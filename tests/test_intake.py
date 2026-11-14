def test_resume_intake_keeps_education_periods_from_pdf_text():
    from app.intake import parse_material

    parsed = parse_material(
        "教育背景\n"
        "中央民族大学（985） - 计算机技术 - 硕士 2023.09 - 2026.07\n"
        "武汉工程大学 - 软件工程（英语双专业） - 本科 2019.09 - 2023.07"
    )

    assert parsed["education"] == [
        {"id": "edu-file-1", "school": "中央民族大学", "degree": "硕士", "major": "计算机技术",
         "start_date": "2023-09", "end_date": "2026-07"},
        {"id": "edu-file-2", "school": "武汉工程大学", "degree": "本科", "major": "软件工程",
         "start_date": "2019-09", "end_date": "2023-07"},
    ]


def test_resume_intake_reads_a_standalone_name_from_the_top_of_uploaded_resume():
    from app.intake import parse_material

    parsed = parse_material(
        "何明鑫\n"
        "求职意向：数据开发 随时到岗\n"
        "19947849581 h19947849581@163.com\n"
        "中央民族大学 - 计算机技术 - 硕士 2023.09 - 2026.07"
    )

    assert parsed["name"] == "何明鑫"


def test_resume_intake_does_not_treat_a_resume_heading_as_a_name():
    from app.intake import parse_material

    parsed = parse_material("教育背景\n中央民族大学 - 计算机技术 - 硕士 2023.09 - 2026.07")

    assert parsed["name"] == ""


def test_intake_api_separates_resume_fields_from_jd_fields(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    source = "姓名：小林\n联系方式：job@example.com\n江城大学 本科 软件工程\n使用 Java 完成查询接口。"
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as client:
        client.get("/api/session")
        parsed = client.post("/api/intake/parse", json={"text": source})
        assert parsed.status_code == 200, parsed.text
        fields = parsed.json()
        assert fields["name"] == "小林"
        assert fields["contact"] == "job@example.com"
        assert fields["education"][0]["school"] == "江城大学"
        assert fields["education"][0]["degree"] == "本科"
        assert fields["education"][0]["major"] == "软件工程"

        noisy = client.post("/api/intake/parse", json={"text": "在江城大学实验室使用 Java 完成查询接口。"})
        assert noisy.json()["education"] == []
        assert noisy.json()["name"] == ""
        jd = client.post("/api/intake/parse", json={"text": "姓名：无关\n岗位：Java 后端", "purpose": "jd"})
        assert jd.json()["name"] == ""
        assert jd.json()["target_role"] == "Java 后端"
