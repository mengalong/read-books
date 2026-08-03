from datetime import datetime, timezone
from time import perf_counter

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import require_admin
from app.services.auth import AuthIdentity
from app.models import ModelConfiguration
from app.schemas import (
    ModelConfigurationResponse,
    ModelConfigurationUpdate,
    ModelConnectionTestRequest,
    ModelConnectionTestResponse,
    PromptPreviewResponse,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    TokenUsageReportResponse,
    TokenUsageStageResponse,
    TokenUsageSummaryResponse,
    TokenUsageTaskResponse,
    TokenUsageUserSummaryResponse,
)
from app.services.model_config import (
    DEFAULT_CONFIGURATION_ID,
    get_effective_model_configuration,
)
from app.services.model_usage import (
    ModelUsageEvent,
    get_model_usage_report,
    get_model_usage_user_summaries,
    new_usage_context,
    record_model_usage,
    token_counts,
)
from app.services.prompt_config import (
    PROMPT_TYPES,
    PROMPT_VARIABLES,
    get_prompt_history,
    get_prompt_template,
    prompt_values_for_preview,
    render_prompt,
    reset_prompt_template,
    save_prompt_template,
    validate_prompt,
)

router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_admin)],
)
settings = get_settings()


def to_response(db: Session) -> ModelConfigurationResponse:
    configuration = get_effective_model_configuration(db, settings)
    return ModelConfigurationResponse(
        id=DEFAULT_CONFIGURATION_ID,
        provider_mode=configuration.provider_mode,
        base_url=configuration.base_url,
        model_name=configuration.model_name,
        timeout_ms=configuration.timeout_ms,
        temperature=configuration.temperature,
        api_key_configured=bool(configuration.api_key),
        last_test_status=configuration.last_test_status,
        last_test_message=configuration.last_test_message,
        last_tested_at=configuration.last_tested_at,
        last_test_latency_ms=configuration.last_test_latency_ms,
        created_at=configuration.created_at,
        updated_at=configuration.updated_at,
    )


def to_prompt_response(prompt) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=prompt.template_id,
        prompt_type=prompt.prompt_type,
        system_prompt=prompt.system_prompt,
        user_prompt=prompt.user_prompt,
        version=prompt.version,
        is_active=prompt.is_active,
        available_variables=list(PROMPT_VARIABLES[prompt.prompt_type]),
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
    )


def prompt_type_or_404(prompt_type: str) -> str:
    if prompt_type not in PROMPT_TYPES:
        raise HTTPException(status_code=404, detail="未找到该提示词类型")
    return prompt_type


@router.get("/model", response_model=ModelConfigurationResponse)
def get_model_configuration(db: Session = Depends(get_db)) -> ModelConfigurationResponse:
    return to_response(db)


@router.put("/model", response_model=ModelConfigurationResponse)
def update_model_configuration(
    payload: ModelConfigurationUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> ModelConfigurationResponse:
    base_url = payload.base_url.strip()
    model_name = payload.model_name.strip()
    if payload.provider_mode == "openai_compatible":
        if not base_url:
            raise HTTPException(status_code=422, detail="真实模型模式需要填写接口地址")
        if not model_name:
            raise HTTPException(status_code=422, detail="真实模型模式需要填写模型名称")
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=422, detail="接口地址必须以 http:// 或 https:// 开头")
    if payload.api_key and payload.clear_api_key:
        raise HTTPException(status_code=422, detail="API Key 不能同时设置和清除")

    stored = db.get(ModelConfiguration, DEFAULT_CONFIGURATION_ID)
    if stored is None:
        stored = ModelConfiguration(id=DEFAULT_CONFIGURATION_ID)
        db.add(stored)

    stored.provider_mode = payload.provider_mode
    stored.base_url = base_url
    stored.model_name = model_name
    stored.scope_type = "platform"
    stored.updated_by_user_id = identity.user.id
    stored.timeout_ms = payload.timeout_ms
    stored.temperature = payload.temperature
    if payload.clear_api_key:
        stored.api_key = ""
    elif payload.api_key and payload.api_key.strip():
        stored.api_key = payload.api_key.strip()
    db.commit()
    db.refresh(stored)
    return to_response(db)


@router.get("/prompts", response_model=list[PromptTemplateResponse])
def get_prompt_templates(db: Session = Depends(get_db)) -> list[PromptTemplateResponse]:
    return [to_prompt_response(get_prompt_template(db, prompt_type)) for prompt_type in PROMPT_TYPES]


@router.get(
    "/prompts/{prompt_type}/history", response_model=list[PromptTemplateResponse]
)
def get_prompt_template_history(
    prompt_type: str, db: Session = Depends(get_db)
) -> list[PromptTemplateResponse]:
    prompt_type_or_404(prompt_type)
    return [to_prompt_response(prompt) for prompt in get_prompt_history(db, prompt_type)]


@router.put("/prompts/{prompt_type}", response_model=PromptTemplateResponse)
def update_prompt_template(
    prompt_type: str,
    payload: PromptTemplateUpdate,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> PromptTemplateResponse:
    prompt_type_or_404(prompt_type)
    try:
        prompt = save_prompt_template(
            db,
            prompt_type,
            payload.system_prompt,
            payload.user_prompt,
            updated_by_user_id=identity.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return to_prompt_response(prompt)


@router.post("/prompts/{prompt_type}/reset", response_model=PromptTemplateResponse)
def reset_prompt(
    prompt_type: str,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> PromptTemplateResponse:
    prompt_type_or_404(prompt_type)
    return to_prompt_response(
        reset_prompt_template(db, prompt_type, updated_by_user_id=identity.user.id)
    )


@router.post("/prompts/{prompt_type}/preview", response_model=PromptPreviewResponse)
def preview_prompt(
    prompt_type: str, payload: PromptTemplateUpdate
) -> PromptPreviewResponse:
    prompt_type_or_404(prompt_type)
    try:
        validate_prompt(prompt_type, payload.system_prompt, payload.user_prompt)
        values = prompt_values_for_preview(prompt_type)
        rendered_system = render_prompt(payload.system_prompt, values)
        rendered_user = render_prompt(payload.user_prompt, values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PromptPreviewResponse(
        prompt_type=prompt_type,
        rendered_system_prompt=rendered_system,
        rendered_user_prompt=rendered_user,
        available_variables=list(PROMPT_VARIABLES[prompt_type]),
    )


@router.get("/token-usage", response_model=TokenUsageReportResponse)
def get_token_usage(
    task_type: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> TokenUsageReportResponse:
    summary, tasks = get_model_usage_report(
        db, task_type=task_type, user_id=user_id, limit=limit
    )
    users = get_model_usage_user_summaries(db, task_type=task_type)
    return TokenUsageReportResponse(
        summary=TokenUsageSummaryResponse(
            task_count=summary.task_count,
            total_calls=summary.total_calls,
            successful_calls=summary.successful_calls,
            failed_calls=summary.failed_calls,
            unreported_calls=summary.unreported_calls,
            input_tokens=summary.input_tokens,
            output_tokens=summary.output_tokens,
            total_tokens=summary.total_tokens,
        ),
        users=[TokenUsageUserSummaryResponse.model_validate(user) for user in users],
        tasks=[
            TokenUsageTaskResponse(
                task_id=task.task_id,
                task_type=task.task_type,
                task_label=task.task_label,
                user_id=task.user_id,
                username=task.username,
                display_name=task.display_name,
                workspace_id=task.workspace_id,
                status=task.status,
                book_id=task.book_id,
                quiz_id=task.quiz_id,
                input_tokens=task.input_tokens,
                output_tokens=task.output_tokens,
                total_tokens=task.total_tokens,
                unreported_calls=task.unreported_calls,
                started_at=task.started_at,
                finished_at=task.finished_at,
                stages=[TokenUsageStageResponse.model_validate(stage) for stage in task.stages],
            )
            for task in tasks
        ],
    )


def model_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])[:300]
        if isinstance(error, str):
            return error[:300]
    except ValueError:
        pass
    return response.text.strip()[:300] or f"HTTP {response.status_code}"


def record_test_result(db: Session, status: str, message: str, latency_ms: int) -> datetime:
    tested_at = datetime.now(timezone.utc)
    stored = db.get(ModelConfiguration, DEFAULT_CONFIGURATION_ID)
    if stored is None:
        stored = ModelConfiguration(id=DEFAULT_CONFIGURATION_ID)
        db.add(stored)
    stored.last_test_status = status
    stored.last_test_message = message[:500]
    stored.last_tested_at = tested_at
    stored.last_test_latency_ms = latency_ms
    db.commit()
    return tested_at


@router.post("/model/test", response_model=ModelConnectionTestResponse)
def test_model_connection(
    payload: ModelConnectionTestRequest,
    db: Session = Depends(get_db),
    identity: AuthIdentity = Depends(require_admin),
) -> ModelConnectionTestResponse:
    base_url = payload.base_url.strip()
    model_name = payload.model_name.strip()
    if not base_url:
        raise HTTPException(status_code=422, detail="请先填写接口地址")
    if not model_name:
        raise HTTPException(status_code=422, detail="请先填写模型名称")
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="接口地址必须以 http:// 或 https:// 开头")
    if payload.api_key and payload.clear_api_key:
        raise HTTPException(status_code=422, detail="API Key 不能同时设置和清除")

    effective = get_effective_model_configuration(db, settings)
    api_key = payload.api_key.strip() if payload.api_key and payload.api_key.strip() else None
    if api_key is None and not payload.clear_api_key:
        api_key = effective.api_key

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    endpoint = base_url if base_url.rstrip("/").endswith("/chat/completions") else (
        f"{base_url.rstrip('/')}/chat/completions"
    )
    started_at = perf_counter()
    usage_context = new_usage_context(
        "model_connection_test",
        f"测试模型连接 · {model_name}",
        user_id=identity.user.id,
        workspace_id=identity.workspace.id,
    )

    def record_connection_usage(
        status: str, body: object = None, error_message: str | None = None
    ) -> None:
        input_tokens, output_tokens, total_tokens = token_counts(body)
        record_model_usage(
            ModelUsageEvent(
                context=usage_context,
                phase="connection_test",
                call_number=1,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                status=status,
                error_message=error_message[:500] if error_message else None,
                latency_ms=round((perf_counter() - started_at) * 1_000),
            )
        )

    try:
        with httpx.Client(timeout=payload.timeout_ms / 1_000) as client:
            response = client.post(
                endpoint,
                headers=headers,
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": "请只回复：连接成功"}],
                    "max_tokens": 16,
                    "temperature": 0,
                    "stream": False,
                },
            )
    except httpx.RequestError as exc:
        latency_ms = round((perf_counter() - started_at) * 1_000)
        message = f"模型接口连接失败：{exc}"
        record_connection_usage("failed", error_message=message)
        tested_at = record_test_result(db, "failed", message, latency_ms)
        return ModelConnectionTestResponse(
            ok=False,
            message=message,
            latency_ms=latency_ms,
            model_name=model_name,
            tested_at=tested_at,
        )

    latency_ms = round((perf_counter() - started_at) * 1_000)
    if not response.is_success:
        body = None
        message = f"模型接口返回 {response.status_code}：{model_error_message(response)}"
        try:
            body = response.json()
        except ValueError:
            pass
        record_connection_usage("failed", body, message)
        tested_at = record_test_result(db, "failed", message, latency_ms)
        return ModelConnectionTestResponse(
            ok=False,
            message=message,
            latency_ms=latency_ms,
            model_name=model_name,
            tested_at=tested_at,
        )
    try:
        body = response.json()
    except ValueError:
        message = "模型接口未返回有效 JSON"
        record_connection_usage("failed", error_message=message)
        tested_at = record_test_result(db, "failed", message, latency_ms)
        return ModelConnectionTestResponse(
            ok=False,
            message=message,
            latency_ms=latency_ms,
            model_name=model_name,
            tested_at=tested_at,
        )
    if not isinstance(body, dict) or not isinstance(body.get("choices"), list) or not body["choices"]:
        message = "模型接口响应不符合 OpenAI 兼容格式"
        record_connection_usage("failed", body, message)
        tested_at = record_test_result(db, "failed", message, latency_ms)
        return ModelConnectionTestResponse(
            ok=False,
            message=message,
            latency_ms=latency_ms,
            model_name=model_name,
            tested_at=tested_at,
        )
    first_choice = body["choices"][0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else None
    model_response = message.get("content") if isinstance(message, dict) else None
    if not isinstance(model_response, str) or not model_response.strip():
        message = "模型接口响应中没有可展示的文本内容"
        record_connection_usage("failed", body, message)
        tested_at = record_test_result(db, "failed", message, latency_ms)
        return ModelConnectionTestResponse(
            ok=False,
            message=message,
            latency_ms=latency_ms,
            model_name=model_name,
            tested_at=tested_at,
        )

    record_connection_usage("success", body)
    tested_at = record_test_result(db, "success", "模型接口连接成功", latency_ms)
    return ModelConnectionTestResponse(
        ok=True,
        message="模型接口连接成功",
        latency_ms=latency_ms,
        model_name=model_name,
        model_response=model_response[:2_000],
        tested_at=tested_at,
    )
