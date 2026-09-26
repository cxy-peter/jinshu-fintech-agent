# V10 恢复验收 · 2026-09-26

- [合并请求](https://github.com/cxy-peter/jinshu-fintech-agent/pull/8)
- [CI浏览器验收](https://github.com/cxy-peter/jinshu-fintech-agent/actions/runs/36269138491)：71核心检查、Linux34项部署工具检查、32项Chromium检查；Windows70项通过/1语义权重未下载跳过，部署33项通过/1系统权限相关项跳过。后续增加的非外发资料回放隔离用例以最新CI为准。
- [线上合成请求记录](v10-live-acceptance.json)：23项线上API检查，包含真正的CPU中文Embedding、混合召回、DeepSeek响应、资料引用、独立审核、持久化和隔离。
- DeepSeek本轮示例返回约1秒；这是一次请求观测，不是延迟SLA。
- 页面视觉与交互证据来自GitHub CI的Chromium；线上通过API验收，未声称覆盖全部生产浏览器交互。
- 已经启用的是私有Blob兼容存储。Atlas、Redis、Milvus、pi仍需用户配置对应服务；没有伪造连接成功。
- 公开合成资料留在演示库方便体验，验收反馈从运营指标删除。没有把用户简历、原项目压缩包、私密业务资料或密钥上传仓库。

源码保持原企业引擎和补丁；数据与服务的准确边界见[恢复说明](../V10_RESTORATION.md)。
