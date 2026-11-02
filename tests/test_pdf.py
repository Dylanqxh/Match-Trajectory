def test_real_chinese_pdf_keeps_all_demo_text_and_can_be_read():
    import pypdfium2 as pdfium
    import pytest

    from app.demo import demo_content
    from app.rendering import font_path, render_pdf

    if not font_path().is_file():
        pytest.skip("需要通过启动环境配置中文字体；M0 发布探针不可跳过此项")
    data = render_pdf(demo_content(), demo=True, draft=False)
    pdf = pdfium.PdfDocument(data)
    try:
        assert len(pdf) <= 2
        text = ""
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                textpage = page.get_textpage()
                try:
                    text += textpage.get_text_range()
                finally:
                    textpage.close()
            finally:
                page.close()
        assert "陈亦宁" in text
        assert "虚构演示" in text
        assert "本人完成预约查询" in text
    finally:
        pdf.close()
