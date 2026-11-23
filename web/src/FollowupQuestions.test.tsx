import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FollowupQuestions } from "./GenerationPanel";

const questions = [{
  id: "emphasis",
  text: "已有材料里，先突出哪一段？",
  kind: "choice" as const,
  options: [
    { id: "recall", label: "先写材料里的离线召回对照", recommended: true },
    { id: "paper", label: "先写材料里的第二作者论文", recommended: false },
  ],
}];

describe("FollowupQuestions", () => {
  it("offers grounded choices with one recommendation and does not preselect them", () => {
    const html = renderToStaticMarkup(<FollowupQuestions questions={questions} choices={{}} notes={{}} busy={false}
      onChoice={() => undefined} onNote={() => undefined} onSubmit={() => undefined} onSkip={() => undefined}/>);

    expect(html).toContain("先写材料里的离线召回对照（推荐）");
    expect(html).toContain("先写材料里的第二作者论文");
    expect(html).not.toContain("checked");
    expect(html).toContain("跳过，先看初稿");
    expect(html).toContain("补充一句，可选");
  });

  it("keeps an older open question editable", () => {
    const html = renderToStaticMarkup(<FollowupQuestions questions={[{ id: "q1", text: "本人交付了什么？", kind: "note" }]}
      choices={{}} notes={{}} busy={false} onChoice={() => undefined} onNote={() => undefined}
      onSubmit={() => undefined} onSkip={() => undefined}/>);

    expect(html).toContain("<textarea");
    expect(html).toContain("本人交付了什么？");
  });
});
