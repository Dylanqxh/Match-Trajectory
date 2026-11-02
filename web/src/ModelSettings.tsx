import { useState } from "react";
import { api } from "./api";

const choices = {
  deepseek: { name: "DeepSeek（候选接入）", model: "deepseek-flash", help: "https://api-docs.deepseek.com/" },
  dashscope: { name: "阿里云百炼 · 北京（候选接入）", model: "qwen-plus", help: "https://help.aliyun.com/zh/model-studio/get-api-key/" },
  custom: { name: "自定义兼容接口", model: "", help: "" },
};
type Choice = keyof typeof choices;

export function ModelSettings({ onClose }: { onClose: () => void }) {
  const [provider, setProvider] = useState<Choice>("deepseek");
  const [model, setModel] = useState("deepseek-flash");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  async function test() {
    setBusy(true); setMessage("");
    try {
      const result = await api<{ message: string }>("/api/model-settings/test", {
        provider, model, api_key: key, base_url: provider === "custom" ? baseUrl : "",
      });
      setKey(""); setMessage(result.message + "。Key 仅保留在本次服务会话中。");
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="模型连接">
    <button className="close" onClick={onClose} disabled={busy} aria-label="关闭模型设置">×</button>
    <div className="eyebrow">连接准备</div><h2>连接你选择的模型</h2>
    <p>当前仅做合成短文本测试，不会发送你的简历。AI 简历生成将在后续阶段接入。</p>
    <fieldset disabled={busy}>
      <label>供应商<select value={provider} onChange={event => {
        const next = event.target.value as Choice; setProvider(next); setModel(choices[next].model); setKey(""); setMessage("");
      }}>{Object.entries(choices).map(([value, choice]) => <option value={value} key={value}>{choice.name}</option>)}</select></label>
      {choices[provider].help && <a href={choices[provider].help} target="_blank" rel="noreferrer">打开官方开通与 Key 说明 ↗</a>}
      {provider === "custom" && <label>接口地址<input value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://…/v1"/></label>}
      <label>API Key<input type="password" autoComplete="new-password" value={key} onChange={e => setKey(e.target.value)} placeholder="粘贴你在供应商取得的 Key"/></label>
      <details><summary>高级：模型名称</summary><label>模型 ID<input value={model} onChange={e => setModel(e.target.value)}/></label></details>
      <button className="primary" onClick={test} disabled={!key || !model}>{busy ? "正在测试…" : "测试并保存到会话"}</button>
    </fieldset>
    {message && <p role="status" className="notice">{message}</p>}
    <p className="fine">供应商可能要求注册、开通和付费；预设尚未完成真实凭据与全流程验证。</p>
  </section></div>;
}
