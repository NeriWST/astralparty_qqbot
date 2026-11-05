"""Small-card upload adapter for qq-botpy 1.2 (which only wraps URL uploads)."""
import base64
import json
import re


class MediaUploadError(RuntimeError):
    pass


def error_code(error):
    """Only expose a platform error code, never raw responses or credentials."""
    data = getattr(error, 'msgs', None)
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            match = re.search(r'[\"\']code[\"\']\s*:\s*(\d+)', data)
            data = {'code': match.group(1)} if match else None
    code = data.get('code') if isinstance(data, dict) else getattr(error, 'code', None)
    return str(code) if isinstance(code, (str, int)) and str(code).isdigit() else 'unknown'


def failure_reason(error):
    if isinstance(error, MediaUploadError) and error.args and error.args[0] in (
            'missing_file_info', 'direct_upload_size_limit'):
        return error.args[0]
    return 'see_stage_and_code'


def checked_media(response):
    if not isinstance(response, dict) or not isinstance(response.get('file_info'), str) or not response['file_info']:
        raise MediaUploadError('missing_file_info')
    return {'file_info': response['file_info']}


async def upload_image(api, target, png, group=False, url=None):
    if url:
        try:
            if group:
                response = await api.post_group_file(group_openid=target, file_type=1,
                                                     url=url, srv_send_msg=False)
            else:
                response = await api.post_c2c_file(openid=target, file_type=1,
                                                   url=url, srv_send_msg=False)
            return checked_media(response)
        except Exception as error:
            print('[cards] stage=url_upload failed; try direct_upload',
                  type(error).__name__, 'code=' + error_code(error), 'reason=' + failure_reason(error))
    # Conservative bound on base64 payload as well as raw PNG size (5 MB API limit).
    if not png or ((len(png) + 2) // 3) * 4 >= 5 * 1024 * 1024:
        raise MediaUploadError('direct_upload_size_limit')
    from botpy.http import Route
    # Reuse SDK authentication, timeout and sandbox routing; do not create another token client.
    path = '/v2/groups/{group_openid}/files' if group else '/v2/users/{openid}/files'
    route = Route('POST', path, **({'group_openid': target} if group else {'openid': target}))
    response = await api._http.request(route, json={
        'file_type': 1, 'file_name': 'stats.png',
        'file_data': base64.b64encode(png).decode('ascii'), 'srv_send_msg': False})
    return checked_media(response)
