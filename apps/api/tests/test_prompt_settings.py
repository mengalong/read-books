def test_prompt_templates_support_preview_versioning_and_validation(client):
    response = client.get("/api/settings/prompts")
    assert response.status_code == 200
    templates = response.json()
    assert {template["prompt_type"] for template in templates} == {"generation", "grading"}
    generation = next(template for template in templates if template["prompt_type"] == "generation")
    assert generation["version"] == 0
    assert "{{source_material}}" in generation["user_prompt"]

    preview = client.post(
        "/api/settings/prompts/generation/preview",
        json={
            "system_prompt": generation["system_prompt"],
            "user_prompt": generation["user_prompt"],
        },
    )
    assert preview.status_code == 200
    assert "sample-chunk-1" in preview.json()["rendered_user_prompt"]
    assert "{{source_material}}" not in preview.json()["rendered_user_prompt"]

    invalid = client.put(
        "/api/settings/prompts/generation",
        json={
            "system_prompt": "只输出 JSON。",
            "user_prompt": "{{unsupported_variable}}",
        },
    )
    assert invalid.status_code == 422
    assert "不支持的变量" in invalid.json()["detail"]

    saved = client.put(
        "/api/settings/prompts/generation",
        json={
            "system_prompt": "自定义系统约束，只输出 JSON。",
            "user_prompt": generation["user_prompt"].replace("总预计用时必须控制在 15 分钟左右", "目标时长为 {{duration_minutes}} 分钟"),
        },
    )
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    assert saved.json()["is_active"] is True

    history = client.get("/api/settings/prompts/generation/history")
    assert history.status_code == 200
    assert [item["version"] for item in history.json()] == [1]

    reset = client.post("/api/settings/prompts/generation/reset")
    assert reset.status_code == 200
    assert reset.json()["version"] == 2
    assert "你只输出符合要求的 JSON" in reset.json()["system_prompt"]

    current = client.get("/api/settings/prompts")
    current_generation = next(item for item in current.json() if item["prompt_type"] == "generation")
    assert current_generation["version"] == 2
