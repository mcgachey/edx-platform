import courseware
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden


def lti_launch(request, course_id, chapter=None, section=None, position=None):
    if not settings.FEATURES["ENABLE_LTI_PROVIDER"]:
        return HttpResponseForbidden()

    lti_parameters = parse_required_parameters(request)
    if not lti_parameters:
        return HttpResponseBadRequest()

    if not verify_oauth_signature(request, lti_parameters):
        return HttpResponseForbidden()

    print lti_parameters["roles"]

    return HttpResponse("TODO: Render refactored courseware view")


def verify_oauth_signature(request, lti_parameters):
    return True


def parse_required_parameters(request):
    params = {}
    for key in ['roles', 'context_id', 'oauth_version', 'oauth_consumer_key', 'oauth_signature',
                 'oauth_signature_method', 'oauth_timestamp', 'oauth_nonce']:
        if key not in request.POST:
            return None
        params[key] = request.POST[key]
    return params


