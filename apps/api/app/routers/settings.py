from time import perf_counter

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ModelConfiguration
from app.schemas import (
    ModelConfigurationResponse,
    ModelConfigurationUpdate,
    ModelConnectionTestRequest,
    ModelConnectionTestResponse,
)
from app.services.model_config import (
    DEFAULT_CONFIGURATION_ID,
    get_effective_model_configuration,
)

router = APIRouter(prefix="/settings", tags=["settings"])
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
        created_at=configuration.created_at,
        updated_at=configuration.updated_at,
    )


@router.get("/model", response_model=ModelConfigurationResponse)
def get_model_configuration(db: Session = Depends(get_db)) -> ModelConfigurationResponse:
    return to_response(db)


@router.put("/model", response_model=ModelConfigurationResponse)
def update_model_configuration(
    payload: ModelConfigurationUpdate, db: Session = Depends(get_db)
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
    stored.timeout_ms = payload.timeout_ms
    stored.temperature = payload.temperature
    if payload.clear_api_key:
        stored.api_key = ""
    elif payload.api_key and payload.api_key.strip():
        stored.api_key = payload.api_key.strip()
    db.commit()
    db.refresh(stored)
    return to_response(db)


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


@router.post("/model/test", response_model=ModelConnectionTestResponse)
def test_model_connection(
    payload: ModelConnectionTestRequest, db: Session = Depends(get_db)
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
        raise HTTPException(status_code=502, detail=f"模型接口连接失败：{exc}") from exc

    latency_ms = round((perf_counter() - started_at) * 1_000)
    if not response.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"模型接口返回 {response.status_code}：{model_error_message(response)}",
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="模型接口未返回有效 JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("choices"), list) or not body["choices"]:
        raise HTTPException(status_code=502, detail="模型接口响应不符合 OpenAI 兼容格式")
    first_choice = body["choices"][0]
    message = first_choice.get("message") if isinstance(first_choice, dict) else None
    model_response = message.get("content") if isinstance(message, dict) else None
    if not isinstance(model_response, str) or not model_response.strip():
        raise HTTPException(status_code=502, detail="模型接口响应中没有可展示的文本内容")

    return ModelConnectionTestResponse(
        ok=True,
        message="模型接口连接成功",
        latency_ms=latency_ms,
        model_name=model_name,
        model_response=model_response[:2_000],
    )
