"""
找回密码（R-08）和两步验证（R-09）的接口。业务规则在 user_access 模块中；
路径与用户权限接口共用 /api/v1/access 前缀，单独成文件以免接口文件过长。
"""

from fastapi import APIRouter, Response

from app.api.replies import responses_for
from app.api.runner import RunDep
from service.user_access import public as access
from shared.public import Nothing

router = APIRouter(prefix="/api/v1/access", tags=["用户权限"])


# 管理员为本组织用户生成一次性重置码，只返回这一次，由管理员交给用户。
@router.post(
    "/users/reset-code",
    summary="生成密码重置码",
    operation_id="issue_reset",
    response_model=access.ResetCode,
    responses=responses_for(access.issue_reset),
)
async def issue_reset(body: access.UserRef, run: RunDep) -> access.ResetCode:
    return await run(access.issue_reset, body)


# 用户用重置码设置新密码；成功后所有设备都需要重新登录。
@router.post(
    "/password/reset",
    summary="用重置码设置新密码",
    operation_id="reset_password",
    status_code=204,
    responses=responses_for(access.reset_password),
)
async def reset_password(body: access.ResetInput, run: RunDep) -> Response:
    await run(access.reset_password, body)
    return Response(status_code=204)


# 登录用户生成两步验证密钥，填进身份验证器应用后再确认开启。
@router.post(
    "/otp",
    summary="生成两步验证密钥",
    operation_id="start_otp",
    response_model=access.OtpSetup,
    responses=responses_for(access.start_otp),
)
async def start_otp(run: RunDep) -> access.OtpSetup:
    return await run(access.start_otp, Nothing())


# 提交当前验证码，开启两步验证。
@router.post(
    "/otp/enable",
    summary="开启两步验证",
    operation_id="enable_otp",
    status_code=204,
    responses=responses_for(access.enable_otp),
)
async def enable_otp(body: access.OtpCode, run: RunDep) -> Response:
    await run(access.enable_otp, body)
    return Response(status_code=204)


# 提交当前验证码，关闭两步验证。
@router.post(
    "/otp/disable",
    summary="关闭两步验证",
    operation_id="disable_otp",
    status_code=204,
    responses=responses_for(access.disable_otp),
)
async def disable_otp(body: access.OtpCode, run: RunDep) -> Response:
    await run(access.disable_otp, body)
    return Response(status_code=204)


# 管理员为本组织用户关闭两步验证（例如手机丢失）。
@router.post(
    "/users/otp/reset",
    summary="管理员关闭两步验证",
    operation_id="reset_otp",
    status_code=204,
    responses=responses_for(access.reset_otp),
)
async def reset_otp(body: access.UserRef, run: RunDep) -> Response:
    await run(access.reset_otp, body)
    return Response(status_code=204)
