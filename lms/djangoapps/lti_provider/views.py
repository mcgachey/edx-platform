import courseware
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from lti_provider.signature_validator import SignatureValidator


def lti_launch(request, course_id, chapter=None, section=None, position=None):
    if not settings.FEATURES["ENABLE_LTI_PROVIDER"]:
        return HttpResponseForbidden()

    lti_parameters = parse_required_parameters(request)
    if not lti_parameters:
        return HttpResponseBadRequest()

    if not SignatureValidator().verify(request):
        return HttpResponseForbidden()

    return render_courseware(course_id, chapter, section, position)


def parse_required_parameters(request):
    params = {}
    for key in ['roles', 'context_id', 'oauth_version', 'oauth_consumer_key', 'oauth_signature',
                'oauth_signature_method', 'oauth_timestamp', 'oauth_nonce']:
        if key not in request.POST:
            return None
        params[key] = request.POST[key]
    return params


def render_courseware(course_id, chapter, section, position):
    return HttpResponse("TODO: Render refactored courseware view")
