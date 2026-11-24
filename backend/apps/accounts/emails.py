"""
Sending GeoAlert's account emails: a plain-text body for any mail app, and
the designed HTML version (templates/accounts/email/) beside it with the
logo attached to the message.

The logo travels inside the email (a cid: image) rather than as a link,
because Gmail can't fetch images from localhost and many inboxes block
remote images until the reader allows them.
"""

from email.mime.image import MIMEImage
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

LOGO_CID = 'geoalert-logo'
LOGO_PATH = Path(__file__).resolve().parent / 'email_assets' / 'logo.png'


def _logo_bytes():
    try:
        return LOGO_PATH.read_bytes()
    except OSError:
        return None  # an email without the logo still goes out


def render_html(template, context, logo=True):
    """The HTML body. Django escapes every value, so a name typed into the admin form can't add markup."""
    return render_to_string(template, {**context, 'logo': LOGO_CID if logo else ''})


def build_message(to, subject, text, template, context):
    """The email for `to`: text, plus the HTML version and its inline logo."""
    logo = _logo_bytes()
    html = render_html(template, {**context, 'subject': subject}, logo=logo is not None)
    message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
    message.attach_alternative(html, 'text/html')
    if logo is not None:
        # 'related' keeps the image with the HTML that shows it, so mail
        # apps draw it in place instead of listing it as an attachment
        message.mixed_subtype = 'related'
        image = MIMEImage(logo, 'png')
        image.add_header('Content-ID', f'<{LOGO_CID}>')
        image.add_header('Content-Disposition', 'inline', filename='geoalert-talisay.png')
        message.attach(image)
    return message


def send(to, subject, text, template, context):
    """Send it; a sending failure is raised for the caller to log."""
    build_message(to, subject, text, template, context).send()
