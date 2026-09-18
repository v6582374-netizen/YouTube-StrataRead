> 2026-09-18 原型阶段记录；源码位置基于 5d28b59。以下为动效建议，不是本次生产实现清单。

# 动效机会：YouTube 阅读文档

此报告只给建议，未将建议写入生产代码。范围是 YouTube 页面，来源为 `surfaces/gui/src/components/YouTubeView.tsx` 的弹层、列表与操作入口，以及原型的新设置入口。代码图谱已更新并定位该视图；当前工具没有 `check_index_coverage`，因此以下证据均以完整视图源码和共享样式的直接读取补充，不作全应用覆盖断言。

应用性格是日常工作工具。共享样式已有 120–180ms 的基础反馈，但没有集中定义弹层 easing token。以下使用技能规定的曲线词汇，若整合时落地，应统一为共享变量，避免页面各自定义。三项均只动 transform/opacity，不动画高度、宽度或模糊半径。

## 1. 通过筛选的机会

| # | Location | Today | Purpose | Frequency | Suggested motion |
| --- | --- | --- | --- | --- | --- |
| 1 | `YouTubeView.tsx:153`；原型“订阅频道 / 生成规则”对话框 | 条件渲染直接出现 | Spatial consistency / Preventing a jarring change | 偶尔配置 | 中心对话框 `opacity:0, transform:translateY(6px) scale(.98)` 到 `opacity:1, transform:none`，200ms，`cubic-bezier(.23,1,.32,1)`；退出沿原路，160ms，`cubic-bezier(.77,0,.175,1)`；全程可关闭与再次打开，从当前呈现值重定向。reduce 下仅 opacity 100ms ease-out。功能收益：明确进入临时设置任务，200ms 内完成且不延迟输入。 |
| 2 | `YouTubeView.tsx:111–112`；原型“自动更新”按钮及弹层 | 弹层无起源提示 | Spatial consistency | 偶尔查看后台状态 | 以按钮附近右上角为 `transform-origin:100% 0`，`scale(.97), opacity:0` 到 `scale(1), opacity:1`，160ms，`cubic-bezier(.23,1,.32,1)`；退出反向120ms同曲线。reduce 下仅 opacity 80ms ease-out。功能收益：清楚知道状态来自哪里，不移动正在阅读的文档。 |
| 3 | `YouTubeView.tsx:125,147`；原型“保存规则 / 复制正文”反馈 | 状态文本直接替换 | Feedback / State indication | 偶尔提交或复制 | 固定位置的成功提示只做 opacity 0→1，140ms，`cubic-bezier(.23,1,.32,1)`；消失 opacity 1→0，100ms同曲线；reduce 下80ms opacity。功能收益：确认保存／复制已发生，不抢焦点、不重复移动内容；提示存续时间与淡入时长独立。 |

Gate 明细：三项均为偶尔操作，分别有明确的空间关系或反馈目的，140–200ms 在预算内，不装饰用户正在阅读的数据，也不阻塞操作。不存在 hover 触发动效，因此没有需要 pointer/hover gating 的保留候选。若后续加入 hover，必须限定 `@media (hover:hover) and (pointer:fine)`。

## 2. 明确拒绝的候选

- `YouTubeView.tsx:126,128–135`，导航、搜索与时间／频道筛选：**频率关淘汰**。高频操作，键盘输入直接生效；不做过渡、不等 debounce 动画。
- `YouTubeView.tsx:142`，文档列表错峰入场或卡片上浮：**功能关淘汰**。用户正在扫读标题，不能为了动感移动内容；过滤结果立即替换。
- `YouTubeView.tsx:114–116`，批次数字滚动与后台状态循环呼吸：**功能关淘汰**。会不断吸引注意力，静态状态点和清晰文字足够。
- 原型频道开关：**频率关限制**。批量排除时可连续操作，不加弹簧或庆祝；立即切换颜色与位置，保存后单次确认。
- 以拖拽、侧滑操作文档：**目的关淘汰**。桌面模块没有自然的空间整理模型，无需引入手势或虚构物理关系。

## 3. Verdict

这个模块只需要极少量动效。最高收益是频道与生成规则对话框的轻量空间过渡；高频的查询、筛选、文档选择保持即时。生产实现的下一步可用 `improve-animations plan 频道与生成规则对话框的200ms空间过渡` 生成独立实施计划，待原型方向选定后再落地。
