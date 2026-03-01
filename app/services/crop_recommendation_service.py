import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from langchain_core.prompts import ChatPromptTemplate

from app.collections.crop_images import (
    get_crop_image_urls_by_crop_names,
)
from app.collections.crop_recommendation import (
    get_crop_recommendation_from_farm_id,
    get_recommended_crop_from_id,
    save_crop_recommendation,
)
from app.collections.crop_recommendation_component import (
    delete_crop_recommendation_components,
    get_crop_recommendation_components,
    save_crop_recommendation_component,
)
from app.collections.cultivating_crop import (
    save_cultivating_crop,
    save_intercropping_details,
)
from app.collections.cultivation_calendar import save_cultivation_calendar
from app.collections.farm_profile import get_farm_profile_from_id
from app.collections.investment_breakdown import save_investment_breakdown
from app.collections.soil_health_recommendations import save_soil_health_recommendations
from app.core.genai_client import get_chat_model
from app.models.ai_workflow import WorkflowType
from app.models.crop_recommendation import (
    RECOMMENDATION_VALIDITY_DAYS,
    CropRecommendationComponent,
    CropRecommendationComponentType,
    CropRecommendationReasoningReport,
    CropRecommendationResponse,
    CropSelectionReasoningReport,
    CropSelectionResponse,
    InterCropRecommendation,
    MonoCrop,
)
from app.models.cultivating_crop import CropState, CultivatingCrop, IntercroppingDetails
from app.models.farm_profile import FarmProfile, WaterSource
from app.prompts.crop_recommendation_system_prompt import (
    CROP_RECOMMENDATION_SYSTEM_PROMPT,
)
from app.prompts.selected_crop_detailer_system_prompt import (
    SELECTED_CROP_DETAILER_SYSTEM_PROMPT,
)
from app.services.ai_workflow_runtime import (
    StreamEmitter,
    WorkflowRuntime,
    sanitize_http_error_message,
)

from .weather_service import get_5_day_3_hour_forecast, get_current_weather


CROP_RECOMMENDATION_VALIDATION_RETRY_PROMPT = """
You are fixing a crop recommendation JSON that failed deterministic validation checks.
Rules:
- Keep response in the exact schema.
- Resolve all validation issues listed in input_json.validation_issues.
- Use current_date and farm water constraints to avoid impossible sowing windows.
- Keep dates realistic for the farm location and season.
"""


SELECTED_CROP_VALIDATION_RETRY_PROMPT = """
You are fixing crop selection planning JSON after deterministic validation errors.
Rules:
- Keep response in exact schema.
- Resolve all validation issues listed in input_json.validation_issues.
- Ensure each cultivation task has from_date <= to_date.
- Avoid past dates relative to input_json.current_date.
- Keep investments grounded to local region assumptions from the farm location.
"""


def _build_structured_chain(model, schema):
    prompt = ChatPromptTemplate.from_messages(
        [("system", "{system_prompt}"), ("human", "{input_json}")]
    )
    return prompt | model.with_structured_output(schema, method="json_schema")


def _crop_name_for_image_lookup(crop: MonoCrop) -> str:
    if crop.crop_name_english and crop.crop_name_english.strip():
        return crop.crop_name_english.strip()
    return crop.crop_name


def _is_recommendation_expired(
    crop_recommendation_response: CropRecommendationResponse,
) -> bool:
    if crop_recommendation_response.expiration_date is None:
        return False
    return crop_recommendation_response.expiration_date < date.today()


def _summarize_weather_for_chunk(weather_forecast) -> dict:
    forecast_items = weather_forecast.list[:8]
    if not forecast_items:
        return {"message": "Forecast unavailable"}

    temps = [item.main.temp for item in forecast_items]
    rain_pop = [item.pop for item in forecast_items]

    return {
        "period_hours": len(forecast_items) * 3,
        "avg_temp_c": round(sum(temps) / len(temps), 1),
        "max_temp_c": max(temps),
        "min_temp_c": min(temps),
        "avg_rain_probability": round(sum(rain_pop) / len(rain_pop), 2),
    }


def _collect_crop_recommendation_date_issues(
    recommendation: CropRecommendationResponse,
    farm_profile: FarmProfile,
    reference_date: date,
) -> list[str]:
    issues: list[str] = []

    def validate_window(label: str, start: date, optimal: date, end: date) -> None:
        if start > end:
            issues.append(f"{label}: start_date is after end_date")
        if not (start <= optimal <= end):
            issues.append(f"{label}: optimal_date must be between start_date and end_date")
        if end < reference_date:
            issues.append(f"{label}: entire sowing window is in the past")

        rain_only = (
            farm_profile.water_source == WaterSource.RAINWATER_HARVESTING
            and farm_profile.irrigation_system is None
        )
        if rain_only and start.month in {2, 3, 4, 5}:
            issues.append(
                f"{label}: rain-dependent farm has sowing window starting in dry season month {start.month}"
            )

    for mono in recommendation.mono_crops:
        validate_window(
            f"mono crop '{mono.crop_name}'",
            mono.sowing_window.start_date,
            mono.sowing_window.optimal_date,
            mono.sowing_window.end_date,
        )

    for inter in recommendation.inter_crops:
        for crop in inter.crops:
            validate_window(
                f"intercrop '{inter.intercrop_type}' crop '{crop.crop_name}'",
                crop.sowing_window.start_date,
                crop.sowing_window.optimal_date,
                crop.sowing_window.end_date,
            )

    return issues


def _collect_crop_selection_date_issues(
    details: CropSelectionResponse,
    reference_date: date,
) -> list[str]:
    issues: list[str] = []
    for idx, calendar in enumerate(details.cultivation_calendar):
        for task in calendar.tasks:
            if task.from_date > task.to_date:
                issues.append(
                    f"cultivation_calendar[{idx}] task '{task.task}': from_date must be <= to_date"
                )
            if task.to_date < reference_date:
                issues.append(
                    f"cultivation_calendar[{idx}] task '{task.task}': task ends in the past"
                )
    return issues


def _ensure_selection_lengths(
    details: CropSelectionResponse,
    expected_count: int,
) -> CropSelectionResponse:
    if len(details.cultivation_calendar) < expected_count:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI returned insufficient cultivation calendar items.",
        )
    if len(details.investment_breakdown) < expected_count:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI returned insufficient investment breakdown items.",
        )

    details.cultivation_calendar = details.cultivation_calendar[:expected_count]
    details.investment_breakdown = details.investment_breakdown[:expected_count]
    return details


def _build_crop_recommendation_components(
    recommendation: CropRecommendationResponse,
) -> list[CropRecommendationComponent]:
    components: list[CropRecommendationComponent] = []

    if recommendation.reasoning_report is not None:
        components.append(
            CropRecommendationComponent(
                recommendation_id=recommendation.id,
                farm_id=recommendation.farm_id or "",
                component_type=CropRecommendationComponentType.REASONING,
                order=0,
                reasoning_report=recommendation.reasoning_report,
            )
        )

    for idx, mono_crop in enumerate(recommendation.mono_crops, start=1):
        components.append(
            CropRecommendationComponent(
                recommendation_id=recommendation.id,
                farm_id=recommendation.farm_id or "",
                component_type=CropRecommendationComponentType.MONO_CROP,
                order=idx,
                mono_crop=mono_crop,
            )
        )

    for inter_idx, inter_crop in enumerate(recommendation.inter_crops, start=1):
        base_order = 1000 + (inter_idx * 100)
        components.append(
            CropRecommendationComponent(
                recommendation_id=recommendation.id,
                farm_id=recommendation.farm_id or "",
                component_type=CropRecommendationComponentType.INTER_CROP,
                order=base_order,
                inter_crop=inter_crop,
            )
        )

        for crop_idx, crop in enumerate(inter_crop.crops, start=1):
            components.append(
                CropRecommendationComponent(
                    recommendation_id=recommendation.id,
                    farm_id=recommendation.farm_id or "",
                    component_type=CropRecommendationComponentType.INTER_CROP_MONO_CROP,
                    order=base_order + crop_idx,
                    inter_crop_id=inter_crop.id,
                    mono_crop=crop,
                )
            )

    return components


def _compose_recommendation_from_components(
    template: CropRecommendationResponse,
    components: list[CropRecommendationComponent],
) -> CropRecommendationResponse:
    mono_crops: list[MonoCrop] = []
    inter_crops: list[InterCropRecommendation] = []
    reasoning_report: Optional[CropRecommendationReasoningReport] = None

    for component in sorted(components, key=lambda item: item.order):
        if (
            component.component_type == CropRecommendationComponentType.REASONING
            and component.reasoning_report is not None
        ):
            reasoning_report = component.reasoning_report

        if (
            component.component_type == CropRecommendationComponentType.MONO_CROP
            and component.mono_crop is not None
        ):
            mono_crops.append(component.mono_crop)

        if (
            component.component_type == CropRecommendationComponentType.INTER_CROP
            and component.inter_crop is not None
        ):
            inter_crops.append(component.inter_crop)

    return CropRecommendationResponse(
        id=template.id,
        farm_id=template.farm_id,
        timestamp=template.timestamp,
        expiration_date=template.expiration_date,
        status=template.status,
        mono_crops=mono_crops,
        inter_crops=inter_crops,
        reasoning_report=reasoning_report or template.reasoning_report,
    )


async def _regenerate_crop_recommendation_for_validation_issues(
    *,
    model,
    input_data: dict,
    validation_issues: list[str],
    previous_output: CropRecommendationResponse,
) -> CropRecommendationResponse:
    correction_chain = _build_structured_chain(
        model=model,
        schema=CropRecommendationResponse,
    )
    correction_input = {
        **input_data,
        "validation_issues": validation_issues,
        "previous_output": previous_output.model_dump(mode="json", by_alias=True),
    }
    return await correction_chain.ainvoke(
        {
            "system_prompt": CROP_RECOMMENDATION_SYSTEM_PROMPT
            + "\n\n"
            + CROP_RECOMMENDATION_VALIDATION_RETRY_PROMPT,
            "input_json": json.dumps(correction_input),
        }
    )


async def _regenerate_crop_selection_for_validation_issues(
    *,
    model,
    input_data: dict,
    validation_issues: list[str],
    previous_output: CropSelectionResponse,
) -> CropSelectionResponse:
    correction_chain = _build_structured_chain(
        model=model,
        schema=CropSelectionResponse,
    )
    correction_input = {
        **input_data,
        "validation_issues": validation_issues,
        "previous_output": previous_output.model_dump(mode="json", by_alias=True),
    }
    return await correction_chain.ainvoke(
        {
            "system_prompt": SELECTED_CROP_DETAILER_SYSTEM_PROMPT
            + "\n\n"
            + SELECTED_CROP_VALIDATION_RETRY_PROMPT,
            "input_json": json.dumps(correction_input),
        }
    )


async def _populate_crop_image_urls(
    crop_recommendation_response: CropRecommendationResponse,
) -> None:
    crop_names: list[str] = []

    crop_names.extend(
        [
            _crop_name_for_image_lookup(crop)
            for crop in crop_recommendation_response.mono_crops
        ]
    )
    for inter_crop in crop_recommendation_response.inter_crops:
        crop_names.extend(
            [_crop_name_for_image_lookup(crop) for crop in inter_crop.crops]
        )

    if not crop_names:
        return

    unique_crop_names = list(dict.fromkeys(crop_names))
    crop_image_urls = await get_crop_image_urls_by_crop_names(unique_crop_names)

    for crop in crop_recommendation_response.mono_crops:
        crop.image_url = crop_image_urls.get(_crop_name_for_image_lookup(crop))

    for inter_crop in crop_recommendation_response.inter_crops:
        for crop in inter_crop.crops:
            crop.image_url = crop_image_urls.get(_crop_name_for_image_lookup(crop))


async def crop_recommendation(
    farm_id: str,
    language: str,
    *,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    stream_emitter: Optional[StreamEmitter] = None,
) -> CropRecommendationResponse:
    workflow = WorkflowRuntime(
        action="crop_recommendation",
        workflow_type=WorkflowType.CROP_RECOMMENDATION,
        emitter=stream_emitter,
        user_id=user_id,
        request_id=request_id,
        farm_id=farm_id,
        metadata={"language": language},
    )
    await workflow.start()

    try:
        await workflow.start_step("check_existing_recommendation")
        prev_crop_recommendation = await get_crop_recommendation_from_farm_id(
            farm_id, include_expired=True
        )
        await workflow.complete_step(
            "check_existing_recommendation",
            {"has_previous": bool(prev_crop_recommendation)},
        )

        if prev_crop_recommendation and not _is_recommendation_expired(
            prev_crop_recommendation
        ):
            await workflow.start_step("reuse_existing_recommendation")
            await _populate_crop_image_urls(prev_crop_recommendation)
            refreshed = await save_crop_recommendation(prev_crop_recommendation)
            await workflow.emit_chunk(
                step="reuse_existing_recommendation",
                chunk_type="recommendation_summary",
                data={
                    "mono_crops": [
                        {
                            "crop_id": crop.id,
                            "crop_name": crop.crop_name,
                            "variety": crop.variety,
                        }
                        for crop in refreshed.mono_crops
                    ],
                    "inter_crops": [
                        {
                            "inter_crop_id": inter.id,
                            "intercrop_type": inter.intercrop_type,
                            "crops": [
                                {
                                    "crop_id": crop.id,
                                    "crop_name": crop.crop_name,
                                    "variety": crop.variety,
                                }
                                for crop in inter.crops
                            ],
                        }
                        for inter in refreshed.inter_crops
                    ],
                },
            )
            await workflow.emit_result(
                refreshed.model_dump(mode="json", exclude_none=True, by_alias=True)
            )
            await workflow.complete_step(
                "reuse_existing_recommendation",
                {"recommendation_id": refreshed.id},
            )
            await workflow.complete({"recommendation_id": refreshed.id, "reused": True})
            return refreshed

        await workflow.start_step("load_farm_profile")
        farm_profile: FarmProfile = await get_farm_profile_from_id(farm_id)

        if not farm_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Farm profile not found.",
            )
        await workflow.complete_step("load_farm_profile", {"farm_id": farm_profile.id})

        await workflow.start_step("load_weather_forecast")
        weather_forecast = await get_5_day_3_hour_forecast(
            farm_profile.location.latitude, farm_profile.location.longitude
        )

        if not weather_forecast:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not retrieve weather forecast. Please try again later.",
            )
        await workflow.emit_chunk(
            step="load_weather_forecast",
            chunk_type="weather_report",
            data=_summarize_weather_for_chunk(weather_forecast),
        )
        await workflow.complete_step("load_weather_forecast")

        grounded_model = get_chat_model(model="gemini-2.5-flash").bind_tools(
            [{"google_search": {}}, {"google_maps": {}}],
            tool_config={
                "retrieval_config": {
                    "lat_lng": {
                        "latitude": farm_profile.location.latitude,
                        "longitude": farm_profile.location.longitude,
                    }
                }
            },
        )
        chain = _build_structured_chain(
            model=grounded_model,
            schema=CropRecommendationResponse,
        )

        input_data = {
            "farm_profile": farm_profile.model_dump(mode="json"),
            "language": language,
            "current_date": date.today().isoformat(),
            "5_d_3_h_weather_forecast": weather_forecast.model_dump(mode="json"),
        }

        await workflow.start_step("generate_reasoning_report")
        reasoning_chain = _build_structured_chain(
            model=grounded_model,
            schema=CropRecommendationReasoningReport,
        )
        reasoning_report: CropRecommendationReasoningReport = await reasoning_chain.ainvoke(
            {
                "system_prompt": CROP_RECOMMENDATION_SYSTEM_PROMPT,
                "input_json": json.dumps(
                    {
                        **input_data,
                        "task": "Build reasoning report and cross verification before creating recommendations",
                    }
                ),
            }
        )
        await workflow.emit_chunk(
            step="generate_reasoning_report",
            chunk_type="reasoning_report",
            data=reasoning_report.model_dump(mode="json", exclude_none=True),
        )
        await workflow.complete_step("generate_reasoning_report")

        await workflow.start_step("generate_crop_recommendations")
        crop_recommendation_response: CropRecommendationResponse = await chain.ainvoke(
            {
                "system_prompt": CROP_RECOMMENDATION_SYSTEM_PROMPT,
                "input_json": json.dumps(
                    {
                        **input_data,
                        "reasoning_report": reasoning_report.model_dump(mode="json"),
                    }
                ),
            }
        )
        crop_recommendation_response.reasoning_report = reasoning_report

        validation_issues = _collect_crop_recommendation_date_issues(
            recommendation=crop_recommendation_response,
            farm_profile=farm_profile,
            reference_date=date.today(),
        )
        if validation_issues:
            await workflow.emit_chunk(
                step="generate_crop_recommendations",
                chunk_type="validation_retry",
                data={"issues": validation_issues},
            )
            crop_recommendation_response = (
                await _regenerate_crop_recommendation_for_validation_issues(
                    model=grounded_model,
                    input_data=input_data,
                    validation_issues=validation_issues,
                    previous_output=crop_recommendation_response,
                )
            )
            crop_recommendation_response.reasoning_report = reasoning_report

        if prev_crop_recommendation:
            crop_recommendation_response.id = prev_crop_recommendation.id
        crop_recommendation_response.farm_id = farm_id
        crop_recommendation_response.timestamp = datetime.now()
        crop_recommendation_response.expiration_date = date.today() + timedelta(
            days=RECOMMENDATION_VALIDITY_DAYS
        )
        await workflow.complete_step(
            "generate_crop_recommendations",
            {
                "mono_crop_count": len(crop_recommendation_response.mono_crops),
                "inter_crop_count": len(crop_recommendation_response.inter_crops),
            },
        )

        await workflow.start_step("persist_recommendation_components")
        await delete_crop_recommendation_components(crop_recommendation_response.id)
        components = _build_crop_recommendation_components(crop_recommendation_response)
        for component in components:
            stored_component = await save_crop_recommendation_component(component)

            if (
                stored_component.component_type
                == CropRecommendationComponentType.MONO_CROP
                and stored_component.mono_crop is not None
            ):
                await workflow.emit_chunk(
                    step="persist_recommendation_components",
                    chunk_type="mono_crop_ready",
                    data={
                        "crop_id": stored_component.mono_crop.id,
                        "crop_name": stored_component.mono_crop.crop_name,
                        "variety": stored_component.mono_crop.variety,
                    },
                )

            if (
                stored_component.component_type
                == CropRecommendationComponentType.INTER_CROP
                and stored_component.inter_crop is not None
            ):
                await workflow.emit_chunk(
                    step="persist_recommendation_components",
                    chunk_type="inter_crop_ready",
                    data={
                        "inter_crop_id": stored_component.inter_crop.id,
                        "intercrop_type": stored_component.inter_crop.intercrop_type,
                        "crops": [
                            {
                                "crop_id": crop.id,
                                "crop_name": crop.crop_name,
                                "variety": crop.variety,
                            }
                            for crop in stored_component.inter_crop.crops
                        ],
                    },
                )

        persisted_components = await get_crop_recommendation_components(
            crop_recommendation_response.id
        )
        crop_recommendation_response = _compose_recommendation_from_components(
            crop_recommendation_response,
            persisted_components,
        )
        await workflow.complete_step(
            "persist_recommendation_components",
            {"component_count": len(persisted_components)},
        )

        await workflow.start_step("save_final_recommendation")
        await save_crop_recommendation(crop_recommendation_response)

        try:
            await _populate_crop_image_urls(crop_recommendation_response)
            crop_recommendation_response = await save_crop_recommendation(
                crop_recommendation_response
            )
        except Exception:
            pass
        await workflow.complete_step(
            "save_final_recommendation",
            {"recommendation_id": crop_recommendation_response.id},
        )
        await workflow.emit_result(
            crop_recommendation_response.model_dump(
                mode="json", exclude_none=True, by_alias=True
            )
        )
        await workflow.complete({"recommendation_id": crop_recommendation_response.id})

        return crop_recommendation_response
    except HTTPException as exc:
        await workflow.fail(
            error_message=sanitize_http_error_message(exc.detail),
            step=workflow.current_step,
            payload={"status_code": exc.status_code},
        )
        raise
    except Exception:
        await workflow.fail(
            error_message="Internal server error. Please try again later.",
            step=workflow.current_step,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )


async def select_crop_from_recommendation(
    farm_id: str,
    crop_recommendation_response_id: str,
    selected_crop_id: str,
    language: str,
    *,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    stream_emitter: Optional[StreamEmitter] = None,
) -> CropSelectionResponse:
    workflow = WorkflowRuntime(
        action="select_crop_from_recommendation",
        workflow_type=WorkflowType.CROP_SELECTION,
        emitter=stream_emitter,
        user_id=user_id,
        request_id=request_id,
        farm_id=farm_id,
        crop_id=selected_crop_id,
        metadata={"language": language, "recommendation_id": crop_recommendation_response_id},
    )
    await workflow.start()

    try:
        await workflow.start_step("load_selection_context")
        farm_profile: FarmProfile = await get_farm_profile_from_id(farm_id)

        if not farm_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Farm profile not found.",
            )

        weather_task = get_5_day_3_hour_forecast(
            farm_profile.location.latitude, farm_profile.location.longitude
        )
        current_weather_task = get_current_weather(
            farm_profile.location.latitude, farm_profile.location.longitude
        )
        recommended_crop_details_task = get_recommended_crop_from_id(
            crop_recommendation_response_id, selected_crop_id
        )

        (
            weather_forecast,
            current_weather,
            recommended_crop_details,
        ) = await asyncio.gather(
            weather_task,
            current_weather_task,
            recommended_crop_details_task,
        )

        if not weather_forecast:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not retrieve weather forecast. Please try again later.",
            )
        await workflow.emit_chunk(
            step="load_selection_context",
            chunk_type="selected_crop_context",
            data={
                "crop_type": (
                    "mono" if isinstance(recommended_crop_details, MonoCrop) else "intercrop"
                ),
                "selected_crop_id": selected_crop_id,
            },
        )
        await workflow.complete_step("load_selection_context")

        grounded_model = get_chat_model(
            model="gemini-2.5-flash",
            thinking_budget=-1,
            include_thoughts=True,
        ).bind_tools(
            [{"google_search": {}}, {"google_maps": {}}],
            tool_config={
                "retrieval_config": {
                    "lat_lng": {
                        "latitude": farm_profile.location.latitude,
                        "longitude": farm_profile.location.longitude,
                    }
                }
            },
        )
        chain = _build_structured_chain(
            model=grounded_model,
            schema=CropSelectionResponse,
        )

        input_data = {
            "farm_profile": farm_profile.model_dump(mode="json"),
            "language": language,
            "current_date": date.today().isoformat(),
            "weather_forecast": weather_forecast.model_dump(mode="json"),
            "current_weather": (
                current_weather.model_dump(mode="json") if current_weather else None
            ),
            "recommended_crop_details": recommended_crop_details.model_dump(
                mode="json"
            ),
        }

        await workflow.start_step("generate_selection_reasoning")
        reasoning_chain = _build_structured_chain(
            model=grounded_model,
            schema=CropSelectionReasoningReport,
        )
        selection_reasoning_report: CropSelectionReasoningReport = (
            await reasoning_chain.ainvoke(
                {
                    "system_prompt": SELECTED_CROP_DETAILER_SYSTEM_PROMPT,
                    "input_json": json.dumps(
                        {
                            **input_data,
                            "task": "Prepare reasoning report before financial/calendar output",
                        }
                    ),
                }
            )
        )
        await workflow.emit_chunk(
            step="generate_selection_reasoning",
            chunk_type="reasoning_report",
            data=selection_reasoning_report.model_dump(mode="json", exclude_none=True),
        )
        await workflow.complete_step("generate_selection_reasoning")

        await workflow.start_step("generate_selection_plan")
        details: CropSelectionResponse = await chain.ainvoke(
            {
                "system_prompt": SELECTED_CROP_DETAILER_SYSTEM_PROMPT,
                "input_json": json.dumps(
                    {
                        **input_data,
                        "selection_reasoning_report": selection_reasoning_report.model_dump(
                            mode="json"
                        ),
                    }
                ),
            }
        )
        details.reasoning_report = selection_reasoning_report

        expected_count = (
            1
            if isinstance(recommended_crop_details, MonoCrop)
            else len(recommended_crop_details.crops)
        )
        details = _ensure_selection_lengths(details, expected_count=expected_count)

        validation_issues = _collect_crop_selection_date_issues(
            details=details,
            reference_date=date.today(),
        )
        if validation_issues:
            await workflow.emit_chunk(
                step="generate_selection_plan",
                chunk_type="validation_retry",
                data={"issues": validation_issues},
            )
            details = await _regenerate_crop_selection_for_validation_issues(
                model=grounded_model,
                input_data=input_data,
                validation_issues=validation_issues,
                previous_output=details,
            )
            details.reasoning_report = selection_reasoning_report
            details = _ensure_selection_lengths(details, expected_count=expected_count)

        await workflow.complete_step(
            "generate_selection_plan",
            {
                "cultivation_calendar_count": len(details.cultivation_calendar),
                "investment_breakdown_count": len(details.investment_breakdown),
            },
        )

        await workflow.start_step("persist_selection_components")

        if isinstance(recommended_crop_details, MonoCrop):
            details.cultivation_calendar[0].crop_id = selected_crop_id
            details.investment_breakdown[0].crop_id = selected_crop_id
            await save_cultivation_calendar(details.cultivation_calendar[0])
            await save_investment_breakdown(details.investment_breakdown[0])
            cultivating_crop: CultivatingCrop = CultivatingCrop(
                id=selected_crop_id,
                farm_id=farm_id,
                name=recommended_crop_details.crop_name,
                variety=recommended_crop_details.variety,
                image_url=recommended_crop_details.image_url,
                crop_state=CropState.SELECTED,
                description=recommended_crop_details.description,
            )

            await save_cultivating_crop(cultivating_crop)
            await workflow.emit_chunk(
                step="persist_selection_components",
                chunk_type="crop_selected",
                data={
                    "crop_id": selected_crop_id,
                    "crop_name": recommended_crop_details.crop_name,
                    "variety": recommended_crop_details.variety,
                },
            )

        if isinstance(recommended_crop_details, InterCropRecommendation):
            for i, crop in enumerate(recommended_crop_details.crops):
                details.cultivation_calendar[i].crop_id = crop.id
                details.investment_breakdown[i].crop_id = crop.id
                await save_cultivation_calendar(details.cultivation_calendar[i])
                await save_investment_breakdown(details.investment_breakdown[i])
                cultivating_crop: CultivatingCrop = CultivatingCrop(
                    id=crop.id,
                    farm_id=farm_id,
                    name=crop.crop_name,
                    variety=crop.variety,
                    image_url=crop.image_url,
                    crop_state=CropState.SELECTED,
                    description=crop.description,
                    intercropping_id=recommended_crop_details.id,
                )
                await save_cultivating_crop(cultivating_crop)
                await workflow.emit_chunk(
                    step="persist_selection_components",
                    chunk_type="intercrop_crop_selected",
                    data={
                        "inter_crop_id": recommended_crop_details.id,
                        "crop_id": crop.id,
                        "crop_name": crop.crop_name,
                        "variety": crop.variety,
                    },
                )
            await save_intercropping_details(
                IntercroppingDetails(
                    id=recommended_crop_details.id,
                    intercrop_type=recommended_crop_details.intercrop_type,
                    arrangement=recommended_crop_details.arrangement,
                    no_of_crops=recommended_crop_details.no_of_crops,
                    specific_arrangement=recommended_crop_details.specific_arrangement,
                    benefits=recommended_crop_details.benefits,
                )
            )

        details.soil_health_recommendations.crop_id = selected_crop_id
        await save_soil_health_recommendations(details.soil_health_recommendations)
        await workflow.emit_chunk(
            step="persist_selection_components",
            chunk_type="soil_health_ready",
            data={
                "crop_id": selected_crop_id,
                "immediate_action_count": len(
                    details.soil_health_recommendations.immediate_actions
                ),
            },
        )
        await workflow.complete_step("persist_selection_components")
        await workflow.emit_result(
            details.model_dump(mode="json", exclude_none=True, by_alias=True)
        )
        await workflow.complete({"selected_crop_id": selected_crop_id})

        return details
    except HTTPException as exc:
        await workflow.fail(
            error_message=sanitize_http_error_message(exc.detail),
            step=workflow.current_step,
            payload={"status_code": exc.status_code},
        )
        raise
    except Exception:
        await workflow.fail(
            error_message="Internal server error. Please try again later.",
            step=workflow.current_step,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error. Please try again later.",
        )
