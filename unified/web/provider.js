"use strict";
// The server is authoritative. A configured key is not a successful inference.
(async function showProvider() {
  const label = document.getElementById("model-provider");
  try {
    const response = await fetch("/api/status", {cache: "no-store"});
    if (!response.ok) throw new Error("status_unavailable");
    const state = await response.json(), model = state.model || {};
    const name = model.provider === "deepseek" ? "DeepSeek" :
      model.provider === "offline_fixture" ? "离线测试夹具（非 DeepSeek）" : "兼容模型";
    label.textContent = `V${state.version} · ${name} · ${model.model || "未设置模型"} · ${model.configured ? "已配置，调用结果见执行记录" : "待配置，未调用"}`;
    label.style.maxWidth = "min(420px, 80vw)";
    label.style.overflowWrap = "anywhere";
    label.title = "配置状态不等于模型可用性。管理员可在服务与配置页同意一次真实模型连接测试。";
  } catch {
    label.textContent = "模型状态暂不可读取；不宣称已接通 DeepSeek";
  }
})();
