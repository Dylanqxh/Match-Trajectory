import { useEffect, useState } from "react";
import { api } from "./api";

const choices = {
  openai: { name: "OpenAI / ChatGPT", model: "gpt-6.1-sol", help: "https://platform.openai.com/api-keys", note: "OpenAI 官方 API · Chat Completions" },
  anthropic: { name: "Anthropic / Claude", model: "claude-sonnet-5", help: "https://console.anthropic.com/settings/keys", note: "Claude 官方 API · Messages" },
  deepseek: { name: "DeepSeek", model: "deepseek-flash", help: "https://api-docs.deepseek.com/", note: "DeepSeek 官方 API · OpenAI 兼容" },
  dashscope: { name: "阿里云百炼", model: "qwen-plus", help: "https://help.aliyun.com/zh/model-studio/get-api-key/", note: "阿里云北京地域 · OpenAI 兼容" },
  custom: { name: "自定义中转站（OpenAI 兼容）", model: "", help: "", note: "填写中转站提供的 Base URL、模型 ID 与 Key" },
};
type Choice = keyof typeof choices;

export function ModelSettings({ onClose, onSaved }: { onClose: () => void; onSaved?: () => void }) {
  const [provider, setProvider] = useState<Choice>("deepseek");
  const [model, setModel] = useState("deepseek-flash");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [connected, setConnected] = useState(false);
  const [remember, setRemember] = useState(false);
  useEffect(() => {
    void api<{ configured: boolean; provider?: Choice; model?: string; base_url?: string }>("/api/model-settings").then(row => {
      if (row.configured && row.provider && row.provider in choices) {
        setConnected(true);
        setProvider(row.provider); setModel(row.model || ""); setBaseUrl(row.base_url || "");
        setMessage(`本次服务已连接 ${row.model}；更换配置时请重新填写 Key 并测试。`);
      }
    }).catch(() => {});
  }, []);
  async function test() {
    setBusy(true); setMessage("");
    try {
      const result = await api<{ message: string }>("/api/model-settings/test", {
        provider, model, api_key: key, base_url: provider === "custom" ? baseUrl : "", remember,
      });
      setKey(""); setConnected(true); setMessage(result.message);
      onSaved?.();
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  async function testTools() {
    setBusy(true); setMessage("");
    try {
      const result = await api<{ message: string }>("/api/model-settings/test-tools", {});
      setMessage(result.message); onSaved?.();
    } catch (error) { setMessage((error as Error).message); }
    finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-label="模型连接">
    <button className="close" onClick={onClose} disabled={busy} aria-label="关闭模型设置">×</button>
    <div className="eyebrow">模型连接</div><h2>使用你自己的 API</h2>
    <p className="model-settings-intro">选择官方服务时只需填写 Key 和模型；使用第三方中转站时再填写 Base URL。连接测试只发送合成短文本，不发送简历。</p>
    <fieldset disabled={busy}>
      <label>供应商<select aria-label="供应商" value={provider} onChange={event => {
        const next = event.target.value as Choice; setProvider(next); setModel(choices[next].model); setKey(""); setMessage("");
      }}>{Object.entries(choices).map(([value, choice]) => <option value={value} key={value}>{choice.name}</option>)}</select></label>
      <div className="provider-summary"><span>{choices[provider].note}</span>
        {choices[provider].help && <a href={choices[provider].help} target="_blank" rel="noreferrer">获取 API Key ↗</a>}
      </div>
      {provider === "custom" && <label>Base URL<input aria-label="接口地址" value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="例如 https://relay.example.com/v1"/><span className="field-hint">必须是 HTTPS；本机服务可使用 http://127.0.0.1。请填写中转站给出的完整兼容地址。</span></label>}
      <div className="model-settings-grid">
        <label>模型 ID<input aria-label="模型 ID" value={model} onChange={e => setModel(e.target.value)} placeholder="填写账号实际可调用的模型"/><span className="field-hint">选择预设后仍可修改为账号实际开通的模型 ID</span></label>
        <label>API Key<input aria-label="API Key" type="password" autoComplete="new-password" value={key} onChange={e => setKey(e.target.value)} placeholder="粘贴 API Key"/><span className="field-hint">只用于本机服务发起调用，页面不会回显</span></label>
      </div>
      <label className="checkbox-label"><input type="checkbox" checked={remember} onChange={event => setRemember(event.target.checked)}/>记住 Key（仅在系统钥匙串可用时保存；否则只留在本次服务内存，重启后要重填）</label>
      <button className="primary full" onClick={test} disabled={!key || !model || (provider === "custom" && !baseUrl)}>{busy ? "正在测试连接…" : "测试并使用此配置"}</button>
      <details><summary>可选：智能修正策略</summary>
        <p className="fine">测试当前已保存模型的工具调用，不发送个人材料。额外发出1次模型请求，可能计费；重新连接后需重新测试。默认生成无需此测试。</p>
        <button className="secondary" onClick={testTools} disabled={!connected}>测试工具调用（1次模型请求）</button>
      </details>
    </fieldset>
    {message && <p role="status" className="notice">{message}</p>}
    <p className="fine">供应商可能要求注册、开通或付费。页面内置的是协议预设，不代表你的账号一定已开通对应模型。</p>
  </section></div>;
}
