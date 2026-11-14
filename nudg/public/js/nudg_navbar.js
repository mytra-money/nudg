// Copyright (c) 2026, NUDG and contributors
// For license information, please see license.txt

(function () {
	if (typeof frappe === "undefined") {
		return;
	}

	frappe.provide("nudg");

	nudg.ALLOWED_ROLES = [
		"System Manager",
		"WhatsApp Manager",
		"WhatsApp User",
		"Sales Manager",
		"Sales User",
	];

	nudg.WHATSAPP_ICON = `
<svg class="nudg-nav-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.883 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
</svg>`;

	nudg.SOUNDS = {
		receive: "/assets/frappe/sounds/alert.mp3",
		send: "/assets/frappe/sounds/submit.mp3",
	};

	nudg.play_sound = function (soundKey) {
		try {
			const soundUrl = nudg.SOUNDS[soundKey];
			if (!soundUrl) return;
			const audio = new Audio(soundUrl);
			audio.volume = 0.35;
			audio.play().catch(() => {
				// Autoplay policy may pause until user gesture
			});
		} catch (e) {
			// silent fallback
		}
	};

	nudg.has_permission = function () {
		if (!frappe.session || !frappe.session.user || frappe.session.user === "Guest") {
			return false;
		}
		if (frappe.session.user === "Administrator") {
			return true;
		}
		const roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		return nudg.ALLOWED_ROLES.some((r) => roles.includes(r));
	};

	nudg.update_badge = function (count) {
		const $badge = $(".nudg-navbar-badge");
		if (!$badge.length) return;

		const num = parseInt(count, 10) || 0;
		if (num > 0) {
			$badge.text(num > 99 ? "99+" : num).show();
		} else {
			$badge.hide().text("");
		}
	};

	nudg.fetch_unread_count = function () {
		frappe.call({
			method: "nudg.api.get_unread_count",
			callback: function (r) {
				if (r && r.message) {
					const count = r.message.needs_reply || r.message.unread || 0;
					nudg.update_badge(count);
				}
			},
		});
	};

	nudg.render_navbar_icon = function () {
		if (!("desk" in frappe) || !nudg.has_permission()) {
			return;
		}

		if (document.querySelector(".nudg-navbar-icon")) {
			return;
		}

		const title = (typeof __ === "function" && __("NUDG")) || "NUDG";
		const html = `
			<li class="nav-item dropdown-mobile nudg-navbar-icon" title="${title}">
				<a class="btn-reset nav-link text-muted" href="/nudg" aria-label="${title}">
					<span class="whatsapp-icon-wrapper">
						${nudg.WHATSAPP_ICON}
						<span class="nudg-navbar-badge" style="display: none;">0</span>
					</span>
				</a>
			</li>
		`;

		const selectors = [
			"header.navbar .navbar-collapse > ul.navbar-nav",
			"header.navbar > .container > .navbar-collapse > ul",
		];

		for (const selector of selectors) {
			const $nav = $(selector);
			if ($nav.length) {
				$nav.prepend(html);
				nudg.fetch_unread_count();
				nudg.bind_realtime();
				return;
			}
		}
	};

	nudg.bind_realtime = function () {
		if (nudg._realtime_bound) return;
		nudg._realtime_bound = true;

		if (frappe.realtime) {
			frappe.realtime.on("nudg_message", function (data) {
				if (data && data.direction === "Incoming") {
					nudg.play_sound("receive");
					nudg.fetch_unread_count();

					// If user is currently in desk, show brief alert toast
					if (window.location.pathname.indexOf("/nudg") === -1) {
						const sender = data.contact_name || data.contact || "WhatsApp";
						frappe.show_alert({
							message: __("New WhatsApp message from {0}", [sender]),
							indicator: "green",
						}, 5);
					}
				}
			});

			frappe.realtime.on("whatsapp_inbox_update", function () {
				nudg.fetch_unread_count();
			});

			frappe.realtime.on("nudg_assignment_update", function () {
				nudg.fetch_unread_count();
			});
		}
	};

	nudg.redirect_agents = function () {
		const path = window.location.pathname || "";
		const onDesk =
			path === "/app" ||
			path.indexOf("/app/") === 0 ||
			path === "/desk" ||
			path.indexOf("/desk/") === 0 ||
			path === "/apps" ||
			path.indexOf("/apps/") === 0;
		if (!onDesk) return;
		const user = frappe.session && frappe.session.user;
		if (!user || user === "Guest" || user === "Administrator") return;
		const roles = (frappe.boot && frappe.boot.user && frappe.boot.user.roles) || [];
		if (roles.indexOf("System Manager") !== -1) return;
		if (frappe.boot && frappe.boot.nudg_block_desk) {
			window.location.replace("/nudg");
			return;
		}
		if (roles.indexOf("WhatsApp Manager") !== -1) return;
		if (roles.indexOf("WhatsApp User") === -1) return;
		window.location.replace("/nudg");
	};

	function setup() {
		if (!frappe.boot || !frappe.session) return;
		nudg.redirect_agents();
		nudg.render_navbar_icon();
	}

	$(function () {
		setup();
		[300, 1000, 2500].forEach((delay) => {
			setTimeout(setup, delay);
		});
	});
})();
