(function () {
  const pendingReference = window.GS_PAYMENT_PENDING_REFERENCE;

  function showAlert(id, type, text) {
    const el = document.getElementById(id);
    if (!el) {
      return;
    }
    el.classList.remove("d-none", "alert-success", "alert-danger", "alert-warning", "alert-info");
    el.classList.add(`alert-${type}`);
    el.textContent = text;
  }

  function toggleLoading(isLoading) {
    const button = document.getElementById("initializeButton");
    const spinner = document.getElementById("initSpinner");
    if (!button || !spinner) {
      return;
    }
    button.disabled = isLoading;
    spinner.classList.toggle("d-none", !isLoading);
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.message || `Request failed (${response.status})`);
    }
    return payload;
  }

  async function initializePayment(event) {
    event.preventDefault();

    const gameId = Number(document.getElementById("gameSelect")?.value || 0);
    const durationMinutes = Number(document.getElementById("durationSelect")?.value || 0);
    const stationCode = document.getElementById("stationSelect")?.value || "station1";
    const csrfToken = document.getElementById("csrfToken")?.value || "";

    toggleLoading(true);
    try {
      const response = await fetchJson("/payments/initialize", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          game_id: gameId,
          duration_minutes: durationMinutes,
          station_code: stationCode,
        }),
      });

      const redirectUrl = response?.data?.authorization_url;
      if (!redirectUrl) {
        throw new Error("Payment gateway did not return checkout URL");
      }
      window.location.href = redirectUrl;
    } catch (error) {
      showAlert("checkoutAlert", "warning", error.message || "Unable to start payment");
    } finally {
      toggleLoading(false);
    }
  }

  async function pollPaymentStatus(reference) {
    const holder = document.getElementById("statusToastHolder");
    const pendingStatusText = document.getElementById("pendingStatusText");
    const retryLink = document.getElementById("retryPaymentLink");

    const intervalId = window.setInterval(async () => {
      try {
        const data = await fetchJson(`/payments/status/${encodeURIComponent(reference)}?refresh=true`);
        const status = data?.data?.status;

        if (!holder) {
          return;
        }

        if (status === "completed" || status === "success") {
          if (pendingStatusText) {
            pendingStatusText.textContent = "Payment completed. Activating your gaming session.";
          }
          holder.innerHTML = '<div class="alert alert-success">Payment confirmed. Redirecting...</div>';
          window.clearInterval(intervalId);
          window.setTimeout(() => {
            window.location.href = `/payments/result/${encodeURIComponent(reference)}`;
          }, 900);
          return;
        }

        if (status === "failed") {
          if (pendingStatusText) {
            pendingStatusText.textContent = "Payment failed. You can retry now.";
          }
          holder.innerHTML = '<div class="alert alert-danger">Payment failed. Redirecting...</div>';
          if (retryLink) {
            retryLink.classList.remove("d-none");
          }
          window.clearInterval(intervalId);
          window.setTimeout(() => {
            window.location.href = `/payments/result/${encodeURIComponent(reference)}`;
          }, 900);
          return;
        }

        if (pendingStatusText) {
          pendingStatusText.textContent = "Waiting for webhook verification from gateway.";
        }
        holder.innerHTML = '<div class="alert alert-info">Awaiting webhook confirmation...</div>';
      } catch (error) {
        if (holder) {
          holder.innerHTML = `<div class="alert alert-warning">${error.message}</div>`;
        }
        if (retryLink) {
          retryLink.classList.remove("d-none");
        }
      }
    }, 3000);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const checkoutAlert = document.getElementById("checkoutAlert");
    const webhookWarning = checkoutAlert?.dataset?.webhookWarning || "";
    if (webhookWarning) {
      showAlert("checkoutAlert", "warning", webhookWarning);
      console.warn(webhookWarning);
    }

    document.getElementById("paystackCheckoutForm")?.addEventListener("submit", initializePayment);

    if (pendingReference) {
      pollPaymentStatus(pendingReference);
    }
  });
})();
