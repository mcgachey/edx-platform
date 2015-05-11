from lms_xblock.runtime import unquote_slashes
from opaque_keys import InvalidKeyError
from opaque_keys.edx.keys import CourseKey, UsageKey


def parse_course_and_usage_keys(course_id, usage_id):
    print "Course ID: {}".format(course_id)
    try:
        course_key = CourseKey.from_string(course_id)
    except Exception as e:
        print "Bad course ID"
        print "Exception: {}".format(e)
        return None, None
    if not course_key:
        return None, None
    try:
        usage_id = unquote_slashes(usage_id)
        usage_key = UsageKey.from_string(usage_id).map_into_course(course_key)
    except InvalidKeyError:
        return None, None
    return course_key, usage_key
