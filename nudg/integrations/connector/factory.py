# Copyright (c) 2026, Nudg and contributors
# For license information, please see license.txt

"""Factory for instantiating the appropriate WhatsApp connector."""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from nudg.integrations.connector.base import (
	BaseWhatsAppConnector,
	WhatsAppConnectorError,
)
from nudg.integrations.connector.meta_cloud import DirectMetaCloudApiConnector
from nudg.integrations.connector.saas_gateway import SaaSGatewayConnector
from nudg.integrations.connector.self_hosted import SelfHostedFrappeConnector

_CONNECTOR_CACHE: dict[str, BaseWhatsAppConnector] = {}


def get_connector(channel: Any = None) -> BaseWhatsAppConnector:
	"""Return the configured connector for an account or explicit connector config.

	Args:
		channel: WA Account name, connector config dict, or None for the site default.

	Returns:
		Instance conforming to BaseWhatsAppConnector.
	"""
	if isinstance(channel, BaseWhatsAppConnector):
		return channel

	channel_doc = None
	if isinstance(channel, str):
		channel_doc = {"channel_name": channel, "connector_type": "Self-Hosted (frappe_whatsapp)"}
	elif getattr(channel, "doctype", None) == "WA Account":
		channel_doc = {"channel_name": channel.name, "connector_type": "Self-Hosted (frappe_whatsapp)"}
	elif isinstance(channel, dict):
		channel_doc = channel
	elif channel is None and frappe.db.exists("DocType", "WA Settings"):
		return _get_singleton("self_hosted", SelfHostedFrappeConnector)

	if not channel_doc:
		raise WhatsAppConnectorError(_("No WhatsApp account is configured."))

	connector_type = (
		getattr(channel_doc, "connector_type", None)
		or (channel_doc.get("connector_type") if isinstance(channel_doc, dict) else None)
	)

	if connector_type == "Self-Hosted (frappe_whatsapp)":
		return _get_singleton("self_hosted", SelfHostedFrappeConnector)
	elif connector_type == "Meta Cloud API Direct":
		return _get_singleton("meta_cloud", DirectMetaCloudApiConnector)
	elif connector_type == "SaaS Gateway / Webhook":
		return _get_singleton("saas_gateway", SaaSGatewayConnector)
	else:
		raise WhatsAppConnectorError(
			_("Unsupported connector type: '{0}'.").format(connector_type)
		)


def get_connector_for_channel(channel: Any) -> BaseWhatsAppConnector:
	"""Alias for get_connector."""
	return get_connector(channel)


def _get_singleton(key: str, factory_cls: type[BaseWhatsAppConnector]) -> BaseWhatsAppConnector:
	if key not in _CONNECTOR_CACHE:
		_CONNECTOR_CACHE[key] = factory_cls()
	return _CONNECTOR_CACHE[key]


def clear_connector_cache() -> None:
	"""Clear the connector instance cache (primarily for unit tests)."""
	_CONNECTOR_CACHE.clear()
