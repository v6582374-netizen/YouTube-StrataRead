# Edison

Edison 将 Openworker 的 macOS 客户端与本地 YouTube 阅读资料库整合在同一工作区。

- 侧边栏 **YouTube**：订阅导入、字幕获取、中文 Markdown、阅读队列、版本与来源追溯。
- **设置 → 模型**：所有模块共用 Openworker 的模型选择、供应商与凭据；YouTube 不需要第二份模型 API Key。
- Google OAuth 仍使用个人客户端和本机 Automic Vault；模型凭据遵循 Openworker 原有存储机制。

## 本地开发

```sh
uv sync --extra dev --extra messaging --extra bedrock --extra browser
cd surfaces/gui
npm ci
npm run tauri dev
```

macOS 客户端入口是 `surfaces/gui`。原有 `desktop` 是旧独立客户端，保留供迁移参考，不再作为 Edison 的入口。现有 YouTube 资料库继续保留在原有用户数据目录，可用 `YOUTUBE_WORKBENCH_WORKSPACE` 指定其他目录。

## 本地应用包

```sh
bash packaging/build_local_macos.sh
```

生成并打开 `surfaces/gui/src-tauri/target/release/bundle/macos/Edison.app`。不依赖上游自动更新或签名发布服务。

## 验证

```sh
uv run pytest
npm --prefix surfaces/gui test
npm --prefix surfaces/gui run build
```

Openworker 上游来源、许可证与原始说明保存在 [docs/upstream/openworker](docs/upstream/openworker)。原 StrataRead 使用说明见 [docs/legacy-strataread-README.md](docs/legacy-strataread-README.md)。
