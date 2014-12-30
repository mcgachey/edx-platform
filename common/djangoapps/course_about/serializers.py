"""
Serializers for all Course Descriptor and Course About Descriptor related return objects.

"""
from lms.djangoapps.courseware.courses import course_image_url, get_course_about_section
from xmodule.modulestore.exceptions import ItemNotFoundError


def _serialize_content(course_descriptor):
    """
    Returns a serialized representation of the course_descriptor and about_descriptor
    Args:
        course_descriptor : course descriptor object

    return:
        serialize data for course information.
    """
    data = dict()
    data['display_name'] = getattr(course_descriptor, 'display_name', None)
    data['start'] = getattr(course_descriptor, 'start', None)
    data['end'] = getattr(course_descriptor, 'end', None)
    data["announcement"] = getattr(course_descriptor, 'announcement', None)
    data['advertised_start'] = getattr(course_descriptor, 'advertised_start', None)
    data['is_new'] = getattr(course_descriptor, 'is_new', None)

    image_url = ''
    if hasattr(course_descriptor, 'course_image') and course_descriptor.course_image:
        image_url = course_image_url(course_descriptor)

    if hasattr(course_descriptor, 'category') and course_descriptor.category == 'course':
        content_id = unicode(course_descriptor.id)
        data['course_number'] = course_descriptor.location.course
    # Other things we do only if the content object is not a course
    else:
        content_id = unicode(course_descriptor.location)
        # Need to use the CourseKey here, which will possibly result in a different (but valid)
        # URI due to the change in key formats during the "opaque keys" transition

    data['course_id'] = unicode(content_id)

    # Following code is getting the course about descriptor information

    course_about_data = _course_about_serialize_content(course_descriptor)
    course_about_data['media']['course_image'] = image_url
    data.update(course_about_data)
    return data


def _course_about_serialize_content(course_descriptor):
    """
    Returns a serialized representation of the about_descriptor

    Args:
        course_descriptor : course descriptor object

    return:
        serialize data for about descriptor.

    """
    data = dict({"media": {"video": None}, "effort": None})
    try:
        video = get_course_about_section(course_descriptor, 'video')
        data["media"]["video"] = video
    except ItemNotFoundError:
        data["media"]["video"] = None
    try:
        effort = get_course_about_section(course_descriptor, 'effort')
        data["effort"] = effort
    except ItemNotFoundError:
        data["effort"] = None
    return data