import courseware
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
import oauth2
from lti_provider.models import LtiConsumer


def lti_launch(request, course_id, chapter=None, section=None, position=None):
    if not settings.FEATURES["ENABLE_LTI_PROVIDER"]:
        return HttpResponseForbidden()

    lti_parameters = parse_required_parameters(request)
    if not lti_parameters:
        return HttpResponseBadRequest()

    if not verify_oauth_signature(request):
        return HttpResponseForbidden()

    return HttpResponse("TODO: Render refactored courseware view")


# TODO: Check that signature method is SHA1
def verify_oauth_signature(request):
    try:
        method = u'POST'
        url = request.build_absolute_uri()
        headers = request.META
        parameters = request.POST.copy()

        oauth_request = oauth2.Request.from_request(
            method,
            url,
            headers=headers,
            parameters=parameters)

        consumer_key = request.POST['oauth_consumer_key']
        consumer_secret = LtiConsumer.objects.get(key=consumer_key).secret

        oauth_consumer = oauth2.Consumer(consumer_key, consumer_secret)

        oauth_server = oauth2.Server()
        signature_method = oauth2.SignatureMethod_HMAC_SHA1()
        oauth_server.add_signature_method(signature_method)

        oauth_server.verify_request(oauth_request, oauth_consumer, {})

    except oauth2.MissingSignature, e:
        return False

    # Signature was valid
    return True


def parse_required_parameters(request):
    params = {}
    for key in ['roles', 'context_id', 'oauth_version', 'oauth_consumer_key', 'oauth_signature',
                 'oauth_signature_method', 'oauth_timestamp', 'oauth_nonce']:
        if key not in request.POST:
            return None
        params[key] = request.POST[key]
    return params


