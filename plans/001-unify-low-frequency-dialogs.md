# 001 — 统一 Edison 低频弹窗的行为与过渡

- **Status**: IMPLEMENTED — 浏览器验收通过；原生 WKWebView 手感待验收
- **Commit**: `756cb47`
- **Date**: 2026-09-21
- **Severity**: HIGH（焦点边界失效）；过渡本身为 MEDIUM
- **Category**: Accessibility / Interruptibility / Cohesion & tokens
- **Estimated scope**: 9 个产品文件、2 个新增 E2E 文件；约 350–550 行净变更。先行为后过渡，作为一个完整任务验收。

## Problem

Edison 是 React 18 + TypeScript + Tailwind + 普通 CSS 的 Tauri 桌面工作区，主入口为 `surfaces/gui`，不是根目录下的旧 `desktop`。没有声明专用动画库。产品以阅读、资料管理为主；仅低频任务弹窗值得过渡，键盘操作与核心导航必须即时。

三个弹窗实现分别承担相似职责，却没有一致的焦点、关闭和视觉生命周期。

### 已复现：Minimalism 新建弹窗的焦点边界失效

`surfaces/gui/src/components/MinimalismView.tsx:747` 当前代码：

```tsx
      {(create || rename) && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={
            rename
              ? mt("重命名集合")
              : create === "asset"
                ? mt("添加物品")
                : mt("新建集合")
          }
          className="fixed inset-0 z-50 bg-black/30 flex items-center justify-center p-5"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setCreate(null);
              setRename(null);
            }
          }}
```

复现路径：打开 Minimalism → 添加物品 → 聚焦“保存” → Tab → 焦点落到 body → Esc，弹窗仍存在。此前在 Chromium 与 WebKit 均观察到。输入框的 `autoFocus` 不构成焦点约束，`aria-modal` 也不自动使背景不可交互。

### 已有可复用的焦点处理，但退出直接卸载

`surfaces/gui/src/components/youtube/Dialog.tsx:25` 当前代码：

```tsx
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current
      ?.querySelector<HTMLElement>("button,input,textarea,select")
      ?.focus();
```

同文件已有 Tab 循环、Esc 监听、关闭后恢复焦点。应把这些职责收敛为共享的表面行为，补足隐藏/禁用元素、背景 inert、输入来源和可打断退出；不要保留两套键盘监听。

`surfaces/gui/src/components/YouTubeView.tsx:529` 当前按模式条件挂载：

```tsx
      {panel === "channels" && (
        <Dialog
          title={yt("订阅频道")}
          subtitle={yt("默认自动生成所有订阅频道的阅读文档。")}
          onClose={close}
```

同文件 `:208` 的关闭函数立即使请求版本失效：

```tsx
  const close = () => {
    panelRevision.current++;
    setPanel(null);
    setPanelMessage("");
    setConfirmDelete(false);
  };
```

必须保留这份即时业务语义。不能为了 200ms 退出效果，把它整个放入定时器。

### 照片/封面预览也有独立外壳和异步关闭

`surfaces/gui/src/components/minimalism/ObjectDossier.tsx:548` 当前代码：

```tsx
      {(preview || inspectedPhoto) && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-6"
          role="dialog"
          aria-modal="true"
          aria-label={preview ? mt("封面预览") : mt("档案照片")}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              void discard();
              setInspectedPhoto(null);
            }
          }}
```

同文件 `:91` 当前 `discard()` 在清理请求结束后才清空预览：

```tsx
  async function discard() {
    if (preview)
      await minimalismCapability("cover.discard", {
        preview: preview.preview,
      }).catch(() => {});
    setPreview(null);
  }
```

关闭反馈不能等待远端临时文件清理。实施前用延迟的 `cover.discard` 响应，通过真实页面点击复现这条路径；本计划不把它描述成已经 E2E 验证的故障。

### 宿主保活约束

`surfaces/gui/src/App.tsx:1765` 当前代码：

```tsx
      {minimalismOpened && <div className={surface === "minimalism" ? "flex flex-1 min-w-0 overflow-hidden" : "hidden"}>
        <MinimalismView onImageSettings={() => openSettings("image-generation")} />
      </div>}
```

Minimalism 切换出去后仍挂载。若共享浮层移到 `document.body`，只隐藏祖先将不再隐藏浮层。必须显式传递页面是否活动并清理，不能靠父组件卸载。

## Target

### 范围与唯一架构

新增一个轻量 `surfaces/gui/src/components/ModalSurface.tsx`，作为唯一负责模态行为、焦点和视觉生命周期的组件。将现有 YouTube Dialog 的相关逻辑提取进去；原 `youtube/Dialog.tsx` 保留为标题、正文、底栏的外观适配器。Minimalism 的表单/预览直接使用同一表面。

仅迁移：

1. YouTube：订阅频道、连接 YouTube、文档信息。
2. Minimalism：添加物品、新建集合、重命名集合。
3. Minimalism 物品档案：档案照片、AI 封面预览。

每个业务区域只保留一个稳定的表面实例，不能给每种内容分别创建竞争焦点的浮层；YouTube 从订阅切到连接是同一浮层内的内容替换，不做关旧开新的双层过渡。

### 参数与输入规则

| 场景 | Transform | Opacity | 时间 | 曲线 |
| --- | --- | --- | --- | --- |
| 指针打开 | `scale(0.97)` → `scale(1)` | 0 → 1 | 200ms | `cubic-bezier(0.23, 1, 0.32, 1)` |
| 指针关闭 | 当前值 → `scale(0.97)` | 当前值 → 0 | 200ms | `cubic-bezier(0.23, 1, 0.32, 1)` |
| 遮罩 | 无 transform | 与打开/关闭同步 | 200ms | 同上 |
| 减少动态 | 始终 `transform: none` | 打开/关闭淡入淡出 | 200ms | 同上 |
| 键盘打开、Esc、键盘取消/提交后的关闭 | 直接设置最终值 | 直接设置最终值 | 0ms，无 Animation 实例 | 不适用 |
| 页面离开、宿主卸载 | 立即撤去表面 | 不留退出残影 | 0ms | 不适用 |

原点 `center center`；表面无平移、无弹跳；背景不移动。此表是最终实施参数。前一轮建议中的镜像退出曲线并非已实现的产品约定：本计划依 `improve-animations` 的出入场 ease-out 规则统一使用现有强 ease-out，避免退出先慢后快。减少动态用 playbook 的 200ms 透明度反馈。

只允许 compositor 属性 `transform` / `opacity`。不动画尺寸、位置布局、颜色、阴影、blur；不加 hover 动效，不加库，不用 CSS `@keyframes` 重播固定起点。

基础样式目标（宽度由 `surfaceClassName` 的业务变体提供）：

```css
:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --duration-modal: 200ms;
}
.modal-scrim {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--scrim);
}
.modal-surface {
  max-width: 100%;
  max-height: calc(100dvh - 48px);
  min-height: 0;
  overflow: auto;
  background: var(--panel);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 24px 75px #0003;
  transform-origin: center center;
}
.modal-scrim[data-modal-state="closing"] {
  pointer-events: none;
}
@media (prefers-reduced-motion: reduce) {
  .modal-surface { transform: none; }
}
@media (prefers-contrast: more) {
  .modal-surface { border-color: var(--ink); }
}
```

不用CSS transition与WAAPI叠加控制同一属性。YouTube保留其正文滚动/固定头尾布局，最外层 `overflow:hidden`、内部 `min-height:0; overflow:auto` 可按原结构覆盖；不得形成两个同时可滚动的嵌套正文容器。

### 视觉所有权与关闭语义

- `open` 是业务事实；`present` 是组件内视觉残留。业务 `open=false` 必须立即撤销活动 role/aria-modal、焦点约束、背景 inert、滚动锁，并恢复合法焦点；残留只在指针退出时短暂存在。
- 退出残留 `aria-hidden=true`、`inert=true`、`pointer-events:none`；保留最后一次打开时的内容与尺寸，避免父级清空数据时先闪成空壳。退出残留不能执行保存/删除，也不能发起新的业务请求。
- 最多缓存一次完整的 React 内容快照，不克隆 DOM，不截图模拟 UI。正在打开时始终显示实时内容，不冻结加载状态。
- 同一实例在退出中重开：从当前显示的 transform/opacity 接回，不能先归零、不能让旧完成回调卸载新内容。
- 初次打开：提交 DOM 时就设置正确的起点、焦点和模态约束，避免首帧以最终状态闪现。
- 键盘关闭发生在进入动画中：立即取消动画、关闭，不能先播完进入。

### 一个最小组件接口

```tsx
type ModalInput = "pointer" | "keyboard";
type ModalCloseReason = "escape" | "backdrop";
type ModalSurfaceProps = {
  open: boolean;
  active?: boolean; // 默认 true；保活页面必须显式传递
  label: string;
  children: React.ReactNode; // 完整的内容表面内部，不含额外遮罩
  surfaceClassName?: string;
  openInput: ModalInput;
  closeInput: ModalInput;
  dismissOnBackdrop?: boolean;
  initialFocusRef?: React.RefObject<HTMLElement>;
  returnFocusRef: React.MutableRefObject<HTMLElement | null>;
  fallbackFocusRef?: React.RefObject<HTMLElement>;
  onRequestClose: (reason: ModalCloseReason, input: ModalInput) => void;
};
```

不增加全局 ModalProvider、事件总线或通用多层浮窗管理器。此范围不支持堆叠模态。表面 class 只控制原有宽度、内边距等外观；业务状态仍属于原业务组件。

### 模态行为

- Portal 到 body 下专用容器；遮罩固定全屏、z-index 50、24px 边距。保持 YouTube 600px/文档470px、新建384px/预览512px 的宽度，受可用视口限制；最大高度 `calc(100dvh - 48px)`，长内容在表面内部滚动。
- 背景现有可交互 body 子树（包括 `#root` 与通知 portal）在活动模态期间 inert，记录并恢复各自原值。用一个仅观察 body 直接子节点的 MutationObserver 覆盖模态期间新挂载的外部 portal；排除自己的 portal。关闭即断开 observer、恢复属性。不得给包含自己浮层的祖先加 inert。
- 初始焦点顺序：调用方明确指定的名称输入框/预览取消按钮；否则第一个可见且可用的控件；否则表面自身 `tabIndex=-1`。不依赖 React autoFocus 的执行先后来记住触发器。
- 每次 Tab 重新枚举可用、可见、非 inert、`tabIndex >= 0` 控件；包含 button、input、select、textarea、链接、summary、显式 tabindex 和 contenteditable，排除隐藏 input 与关闭 details 内隐藏内容。正向/反向循环；零控件时留在表面。若 focusin 落到外部，回到安全焦点。
- Esc 在活动模态处消费，`preventDefault` + `stopPropagation`；输入法 composing 时不要关闭。禁止注册多套 document Esc 处理器。
- 遮罩关闭只在同一次主指针按下和释放都落在遮罩时提交；pointercancel 或从表面拖到遮罩不关闭。在此次迁移中保留产品既有策略：YouTube `dismissOnBackdrop=true`；Minimalism 表单与预览为 false，避免改变有编辑内容的取消习惯。
- 关闭恢复原触发器（仍连接、可见、可用时）；触发器已因新建跳转被移除，则用调用方指定的活动页面后备焦点。只在关闭前焦点确实属于该模态时恢复，不抢走外部已经明确取得的焦点。
- 宿主离开时，绝不聚焦已隐藏页面内的触发器；让目标页面取得焦点。所有 effect 必须经得起 React StrictMode 的 setup/cleanup 重跑，不残留 inert、事件监听、RAF 或 Animation。

## Repo conventions to follow

- `surfaces/gui/src/components/youtube/progress.css:4` 已定义 `--ease-out: cubic-bezier(.23, 1, .32, 1)`。将相同值提升到 `surfaces/gui/src/styles.css` 的 `:root`，移除 progress 的局部重复定义，原进度动效继续继承相同值。
- 新增共享时长 `--duration-modal: 200ms`。运动由共享表面读取这两个 token；不要在三个业务组件中分别写常量。
- `styles.css` 已有 `--panel`、`--line`、`--scrim` 和明暗主题。共享表面使用这些值、1px 边界、16px 圆角、`0 24px 75px #0003` 阴影，不再由不同遮罩硬编码 black/30、black/40。
- 继续使用 `yt()` / `mt()` 翻译；所有既有可访问名称保留。可新增 aria-labelledby/id，但不能依赖硬编码英文作为业务内容。
- `NoticeStack.tsx` 是已有 createPortal 示例；它不是模态实现，不能照搬其键帧入场。
- 当前工作区已有用户未提交修改，尤其 YouTubeView.tsx/progress.css。必须基于当前工作区小范围编辑，保留其连接逻辑与同步改动。

## Steps

1. **先从用户路径复现并落回归。** 新增 `surfaces/gui/e2e/modal-behavior.spec.ts`，复用 `./fixtures`，补齐 Minimalism mock 的 archive 集合，避免不完整夹具产生假空列表。先用“添加物品 → 保存 → Tab → Esc”捕获现状；另以延迟 cleanup 请求检查预览关闭。首轮错误必须来自产品行为，而非定位器歧义。不得连接真实 Google 账户或真实用户资料库。

2. **提取 ModalSurface 的无动效行为。** 从 `youtube/Dialog.tsx` 移入焦点恢复、Esc 和 Tab 处理，再补完整的模态契约。body portal + inert 保存/恢复 + 背景滚动锁全部在同一组件内完成。滚动锁仅保存/恢复必要的 body overflow 原值，不覆盖内联样式整串。先让三个业务区域用同一表面，确保无动效时全部通过焦点验收。

3. **记录交互来源，不能看动画结束时的最后一次按键。** 每个宿主用 ref 在 `onPointerDownCapture` / `onKeyDownCapture` 记录输入与实际触发控件；原生键盘合成 click、辅助技术或无法判断的来源按 keyboard 处理。打开动作同步复制来源与触发器，发生在任何 await 之前；异步完成沿用这次操作的来源，不能根据后来打字改变结果。关闭按钮和提交动作同理复制 closeInput；表面 Esc 明确传 keyboard，遮罩传 pointer。普通业务回调无需接受 DOM 事件，避免把原来的 `onClick={close}` 意外当成枚举参数。只允许事件来源 ref，不建立全局输入状态库。

4. **接入 YouTube 的单一稳定 Dialog。** 将三个 `panel === ... && <Dialog>` 合并为一个常驻 `<Dialog open={panel !== null}>`。按 panel 派发 header/body/footer 内容，保持 panelRevision、加载、错误、同步、删除等业务逻辑。`close()` 立即执行原四项操作；Dialog 仅保留最后可见的 presentation。订阅 → 连接这种 `open` 未变的内容替换不播放表面进出动画，不恢复外部焦点；若旧焦点消失，将焦点放到新内容的安全控件。禁止通过 React key 强制重建整个表面。

5. **接入 Minimalism 表单与预览。** 新建/重命名的 form 成为 ModalSurface 的 children，去掉独立遮罩、重复 role/Esc 和自动焦点，显式引用名称输入框。ObjectDossier 同理迁移预览壳，初始焦点为取消/关闭。使用一个共享预览表面；照片与封面保持原图片尺寸和操作。原生 window.confirm 不迁移。

6. **把异步资源清理与界面关闭分离。** 对 `discard()`，先捕获要清理的 preview ID，立即清空当前预览/照片并启动视觉退出，随后 await 清理该 ID；迟到回调不得再清空后来的新预览。对生成请求增加最小的请求版本/活动检查：关闭、离开或新请求令旧结果失效，旧结果若创建了临时 preview 则清理它，不能重新打开浮层。“重新生成”期间保留当前表面与旧图，禁用旧图采用、允许取消；新结果就绪后替换，避免先关再开的闪烁。验证断网/失败不把用户锁在浮层内。

7. **处理保活页面。** App 的 MinimalismView 调用仅增加 `active={surface === "minimalism"}`；MinimalismView 将 active 传给表面和 ObjectDossier。active=false 时立即终止模态行为与残影、使相关异步结果失效并清空临时弹窗状态；保留物品选择、列表筛选与正文编辑草稿。⌘, 仍然可以打开设置；不要靠禁止全局快捷键回避清理。YouTube 整体卸载走同样的 effect 清理。

8. **增加可打断的视觉生命周期。** 在 ModalSurface 内使用原生 WAAPI，不引入第三方动画库。对表面仅写完整 transform 字符串与 opacity，对遮罩仅写 opacity。采用下述算法；不在业务组件里复制动画逻辑。

   - 目标变化时先读取该元素的实时 `getComputedStyle` transform/opacity，再 cancel 旧 Animation；不可先 cancel 再取值。
   - 更新底层样式为目标值，用 `element.animate([presentation, target], {duration, easing})` 从读到的值过渡。初次挂载使用已知隐藏起点。键盘来源、active=false 或缺少 animate API 时直接落目标，不创建动画。
   - 每次新目标递增本地 generation；监听 Animation.finished，取消的 rejection 显式吸收。只有 generation 相符且仍处于 closing 才清除 present 和快照。严格限制为最多一个表面动画、一个遮罩动画；不能依赖 setTimeout(200) 卸载。
   - Enter/exit 期间持续响应输入。reopen 把退出中的同一 DOM 接回；老 generation 不可影响新一轮。
   - matchMedia('(prefers-reduced-motion: reduce)') 实时订阅；减少动态时 transform 始终 none，只做200ms淡入淡出。偏好在动画中改变时取消位移动画并落到无缩放状态，按当前 opacity 续接。CSS 同时提供 reduced-motion 的 transform:none 后备。
   - 逻辑关闭立即移除可交互语义、释放背景、恢复焦点；WAAPI只管理不可交互的退场影像。为测试增加 `data-modal-state="entering|open|closing"`，无动画的 closed 不保留 DOM。

9. **收敛样式和清理旧实现。** `styles.css` 增加 `.modal-scrim` / `.modal-surface` 基础样式及共享token；`youtube.css` 删除旧 `.yp-scrim` 的职责，`.yp-dialog` / `.yp-detail` 仅保留业务尺寸和内容布局。不再叠两层圆角、遮罩、边框或阴影。高对比模式使用明确 ink 边界；本次表面用实色，不添加 backdrop-filter，因而 reduced-transparency 天然成立。移除迁移后重复的焦点/Esc实现。

10. **补 E2E 与双引擎配置并完成手感验收。** 新增 `surfaces/gui/playwright.modal.config.ts`，继承基础 Playwright 配置，仅匹配 `modal-behavior.spec.ts`，添加 Desktop Chrome 与 Desktop Safari 两项目，workers=1。不安装包、不改锁文件。完整通过下述回归后更新本计划与 README 状态。

## Boundaries

- 允许修改：`ModalSurface.tsx`（新增）、`youtube/Dialog.tsx`、`YouTubeView.tsx`、`MinimalismView.tsx`、`minimalism/ObjectDossier.tsx`、`App.tsx`（仅活动状态传递）、`styles.css`、`youtube/youtube.css`、`youtube/progress.css`（仅移除重复曲线声明），以及上述两个 E2E 文件。必要时仅更新现有 YouTubeView 测试的浮层容器查询。
- 不触及搜索/命令面板、核心路由动画、按钮按压、管理菜单、封面占位文字、通知动效、进度动效、聊天窗口、原生确认框。这些都是独立任务。
- 不改 API 合约、数据持久化、钥匙串、模型/翻译配置和授权规则；异步变更只限防止迟到结果重新打开/误清预览及把cleanup移出关闭关键路径。
- 不新增依赖、ModalProvider、全局动画引擎、定时器卸载补丁或跨路由共享元素动画。
- 不把所有按钮/表面统一颜色；本计划仅统一模态外壳与行为，保留正文排版及现有文案。
- 如果当前实现已偏离上述关键契约，先重新定位核实：已等价修复则缩减范围；若需要改变授权流程/产品语义，记录阻点并报告，不照旧行号覆盖文件。

## Verification

### Mechanical

所有命令从仓库根目录运行。计划编写阶段不执行这些构建/测试；由执行者在实际改动后执行。

```sh
cd surfaces/gui
npx tsc --noEmit
npm test -- src/components/YouTubeView.test.tsx
npx playwright test -c playwright.modal.config.ts
npx playwright test e2e/youtube.spec.ts e2e/minimalism.spec.ts --workers=2
npm run build
```

预期：类型与构建通过，既有流程保持通过，新回归在 Chromium/WebKit 都通过。

新增 E2E 至少覆盖：

| 场景 | 断言 |
| --- | --- |
| 添加物品 → 最后按钮 Tab、首控件 Shift+Tab | 焦点始终在可用控件中循环；Esc 即刻关闭，回到添加按钮 |
| 预览取消，清理响应延迟2秒 | Esc/取消不等网络；清理仍只针对原 ID；新开预览不被旧完成回调清空 |
| 生成后取消/页面离开，再收到迟到结果 | 不重开、不抢焦点，临时资源得到清理 |
| 禁用、隐藏、关闭details控件；零可聚焦控件 | 不落入隐藏元素；最坏落到表面自身，不逃到 body |
| 背景、侧栏、通知 | 活动模态期间不可获得焦点；关闭后恢复各自原有 inert 与滚动状态 |
| 指针进出 | 表面/遮罩采用指定属性和200ms曲线；无尺寸/blur动画 |
| 指针关闭后50ms内重开 | 旧退出不会删除新内容；首帧接近关闭前presentation，无0→1重播 |
| 键盘 Enter/Space 打开、Esc关闭，包括进入中Esc | 不创建模态 Animation；焦点即时正确 |
| 减少动态及运行中切换偏好 | 无transform运动，保留透明度反馈；键盘仍0ms |
| 订阅 → 连接 | 只有一个活动dialog，不播放双层退出/进入，不闪回页面焦点 |
| 模态中⌘,前往设置，再返回Minimalism | 无悬挂portal/inert/焦点锁；页面草稿未丢失 |
| 快速点击保存 | 既有busy语义保持；不会因动画或新绑定重复提交 |
| 800/1100/1440px，中文/英文，明/暗 | 控件不裁切，长弹窗可内部滚动，名称与按钮保持可读 |

轮转与时序检查使用真实 DOM 和 `getAnimations()`，不要仅验证 class 名称。连续帧采样至少检查 opacity/transform 在逆向前后的连续性，容许一帧进度差；不把同一毫秒硬编码相等作为稳定性判据。复用现有真临时资料库 Minimalism 测试验证创建/生成/采用/返回，不碰个人库。

### Feel check

- 指针打开订阅、新建物品和预览：表面中心轻微形成，无弹跳；遮罩与表面同时开始，正文不挪动。
- 在 DevTools Animations 中用10%速度检查开→关→再开，不应闪白、塌空、出现两个可点击表面。检查完成时无一帧回弹到旧transform。
- 键盘 Tab/Shift+Tab/Enter/Space/Esc 连续操作，全程不等待动画；关闭后直接继续键盘操作页面。
- 在200ms退出期间立即点击原触发器，能重开；退出残影不吞点击。
- 勾选系统减少动态，仍有柔和透明度确认，没有缩放；高对比下边界可辨。
- macOS Tauri 开发窗口实测一次以上交互、⌘,页面离开、缩窄窗口和长内容滚动。Playwright WebKit 只是浏览器引擎验证，不能代替真实 WKWebView 手感结论。

### Done when

复现用例在改动前确实暴露焦点问题、改动后通过；指定三类弹窗只使用一份模态行为；键盘零等待；指针过渡可打断；没有迟到回调重开或误清新内容；背景/焦点/滚动总能恢复；双引擎与原有数据生命周期回归通过；完成并记录真实桌面与慢速观感检查。若无法运行原生窗口，明确保留该项未验收，不能标称“像素级验收完成”。

## Evidence and freshness

计划基于上述提交上的当前工作区，含已有未提交变更。路径定位使用 code-review-graph MCP：Edison 索引 `2026-09-21T11:49:39`，SHA与HEAD一致；Dialog importer查询完整返回YouTubeView一个调用文件。会话未提供 codebase-memory 的 check_index_coverage，不能证明图覆盖完整；关键引用全部回读了当前源文件，其他路径不做穷尽声明。

此前截图与复现记录位于 `reports/polish-audit-2026-09-21/`，不是修复完成证据。该报告中的实测焦点缺陷已复核记录；本计划新增的延迟清理、后台保活与迟到结果用例由执行者先在E2E场景确认。


## Implementation result — 2026-09-21

已统一三类弹窗的共享表面、焦点与背景隔离、200ms 可打断过渡、键盘即时操作和减少动态。预览关闭不等待资源清理，迟到生成/采用/表单保存不能关闭或污染新一轮弹窗。错误留在活动模态内。

验收记录与截图见 [modal-polish 报告](../reports/modal-polish-2026-09-21/verification.md)。38 项双引擎用例、206 项单元测试、指定 5 项真实资料库/YouTube 回归及生产构建通过。测试使用当前工作区，包括原有未提交连接与同步变更；提交仅包含本次工作。

原生窗口未验收：检测到正在运行的用户 Edison 正式实例，应用单实例机制会将第二次启动转交该窗口；本次保留现有实例，未替换或重启。WebKit 浏览器检查不代表 WKWebView 手感通过。计划不标记为像素级最终验收完成。
