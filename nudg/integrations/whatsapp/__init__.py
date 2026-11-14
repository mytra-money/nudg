"""Adapter package for the official ``whatsapp`` app.

Import this package from the rest of NUDG. Do not import
``whatsapp.*`` anywhere else. Official imports live in ``adapter`` and run
inside functions, so this desk still imports when that app is not installed.
"""

from nudg.integrations.whatsapp.adapter import (
	get_integration_status,
	get_messages,
	is_installed,
	missing_doctypes,
	send_message,
	send_template,
)

__all__ = [
	"get_integration_status",
	"get_messages",
	"is_installed",
	"missing_doctypes",
	"send_message",
	"send_template",
]
