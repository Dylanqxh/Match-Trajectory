import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CustomProtocolSelector, ModelSettings } from "./ModelSettings";


describe("ModelSettings", () => {
  it("offers popular first-party APIs and a custom relay", () => {
    const html = renderToStaticMarkup(<ModelSettings onClose={() => undefined}/>);

    expect(html).toContain("OpenAI / ChatGPT");
    expect(html).toContain("Anthropic / Claude");
    expect(html).toContain("DeepSeek");
    expect(html).toContain("自定义中转站");
  });

  it("keeps the editable model ID visible in the main form", () => {
    const html = renderToStaticMarkup(<ModelSettings onClose={() => undefined}/>);

    expect(html).toContain('aria-label="模型 ID"');
    expect(html).not.toContain("高级：模型名称");
    expect(html).toContain("选择预设后仍可修改为账号实际开通的模型 ID");
  });

  it("offers explicit Chat Completions and Responses protocols for custom relays", () => {
    const html = renderToStaticMarkup(<CustomProtocolSelector protocol="responses" onChange={() => undefined}/>);

    expect(html).toContain('aria-label="接口协议"');
    expect(html).toContain("Chat Completions");
    expect(html).toContain("Responses");
    expect(html).toContain('value="responses" selected=""');
  });
});
