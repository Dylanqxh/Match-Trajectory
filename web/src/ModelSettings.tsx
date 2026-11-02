import { useEffect, useState } from "react";
import { api } from "./api";

const choices = {
  deepseek: { name: "DeepSeek（候选接入）", model: "deepseek-flash", help: "https://api-docs.deepseek.com/" },
  dashscope: { name: "阿里云百炼 · 北京（候选接入）", model: "qwen-plus", help: "https://help.aliyun.com/zh/model-studio/get-api-key/" },
  custom: { name: "自定义兼容接口", model: "", help: "" },
};
type Choice = keyof typeof choices;

export function ModelSettings({ onClose, onSaved }: { onClose: () => void; onSaved?: () => void }) {
  const [provider, setProvider] = useState<Choice>("deepseek");
  const [model, setModel] = useState("deepseek-flash");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    void api<{ configured: boolean; provider?: Choice; model?: string; base_url?: string }>("/api/model-settings").then(row => {
      if (row.configured && row.provider && row.provider in choices) {
        setProvider(row.provider); setModel(row.model || ""); setBaseUrl(row.base_url || "");
        setMessage(`本次服务已连接 ${row.model}；更换配置时请重新填写 Key 并测试。`);
      }
    }).catch(() => {});
  }, []);
  async function test() {
    setBusy(true); setMessage("");
    try {
      const result = await api<{ message: string }>("/api/model-settings/test", {
        provider, model, api_key: key, base_url: provider === "custom" ? baseUrl : "",
      });
      setKey(""); setMessage(result.message + "。Key 仅保留在本次服务会话中。");
      onSaved?.();
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="模型连接">
    <button className="close" onClick={onClose} disabled={busy} aria-label="关闭模型设置">×</button>
    <div className="eyebrow">连接准备</div><h2>连接你选择的模型</h2>
    <p>此处只用合成短文本测试连接，不发送简历。开始生成时，才会发送你确认的材料。</p>
    <fieldset disabled={busy}>
      <label>供应商<select aria-label="供应商" value={provider} onChange={event => {
        const next = event.target.value as Choice; setProvider(next); setModel(choices[next].model); setKey(""); setMessage("");
      }}>{Object.entries(choices).map(([value, choice]) => <option value={value} key={value}>{choice.name}</option>)}</select></label>
      {choices[provider].help && <a href={choices[provider].help} target="_blank" rel="noreferrer">打开官方开通与 Key 说明 ↗</a>}
      {provider === "custom" && <label>接口地址<input aria-label="接口地址" value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://…/v1"/></label>}
      <label>API Key<input aria-label="API Key" type="password" autoComplete="new-password" value={key} onChange={e => setKey(e.target.value)} placeholder="粘贴你在供应商取得的 Key"/></label>
      <details><summary>高级：模型名称</summary><label>模型 ID<input aria-label="模型 ID" value={model} onChange={e => setModel(e.target.value)}/></label></details>
      <button className="primary" onClick={test} disabled={!key || !model}>{busy ? "正在测试…" : "测试并保存到会话"}</button>
    </fieldset>
    {message && <p role="status" className="notice">{message}</p>}
    <p className="fine">供应商可能要求注册、开通和付费；预设尚未完成真实凭据与全流程验证。</p>
  </section></div>;
}
