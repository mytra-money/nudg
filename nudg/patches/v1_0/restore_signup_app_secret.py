"""Copy the Embedded Signup app secret onto the renamed settings Single.

The DocType rename moved ``tabSingles`` to ``WA Signup Settings`` and left the
encrypted secret under ``WhatsApp Signup Settings``. Login stays closed until
that secret is stored on the new name.
"""

from nudg.integrations.embedded_signup import adopt_legacy_app_secret


def execute():
	adopt_legacy_app_secret()
