"""MQTT Smart Home Bridge for Boss Sentinel.

Publishes presence and status information to an MQTT broker so the
sentinel system can integrate with home-automation platforms such as
Home Assistant, OpenHAB, or Node-RED.

The optional ``paho-mqtt`` package is required for MQTT connectivity.
If it is not installed the bridge degrades gracefully -- every public
method becomes a safe no-op and :attr:`is_connected` always returns
``False``.
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try importing paho-mqtt; if unavailable the module still loads but
# all MQTT operations become no-ops.
try:
    import paho.mqtt.client as mqtt

    _MQTT_AVAILABLE = True
except ImportError:
    mqtt = None  # type: ignore[assignment]
    _MQTT_AVAILABLE = False


class MQTTBridge:
    """MQTT bridge that publishes Boss Sentinel events to a broker.

    Args:
        broker: Hostname or IP address of the MQTT broker.
        port: Broker port (default 1883).
        topic_prefix: Top-level topic prefix for all published messages.
        username: Optional username for broker authentication.
        password: Optional password for broker authentication.
    """

    def __init__(
        self,
        broker: str,
        port: int = 1883,
        topic_prefix: str = "boss_sentinel",
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self.broker = broker
        self.port = port
        self.topic_prefix = topic_prefix
        self.username = username
        self.password = password

        self._client: Optional[Any] = None
        self._connected: bool = False

        if not _MQTT_AVAILABLE:
            logger.warning(
                "MQTTBridge: paho-mqtt is not installed. "
                "MQTT features are disabled. Install with: pip install paho-mqtt"
            )

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Connect to the MQTT broker.

        Returns:
            ``True`` if the connection was initiated successfully,
            ``False`` if paho-mqtt is missing or the connection failed.
        """
        if not _MQTT_AVAILABLE:
            logger.debug("MQTTBridge: skipping connect (paho-mqtt not installed)")
            return False

        try:
            self._client = mqtt.Client(client_id="boss_sentinel", protocol=mqtt.MQTTv311)

            if self.username:
                self._client.username_pw_set(self.username, self.password or "")

            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect

            self._client.connect(self.broker, self.port, keepalive=60)
            # Start a background network loop so callbacks fire
            self._client.loop_start()
            logger.info("MQTTBridge: connecting to %s:%d", self.broker, self.port)
            return True
        except Exception as exc:
            logger.error("MQTTBridge: connection failed: %s", exc)
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker and stop the network loop."""
        if self._client is None:
            return

        try:
            self._client.loop_stop()
            self._client.disconnect()
            logger.info("MQTTBridge: disconnected from %s:%d", self.broker, self.port)
        except Exception as exc:
            logger.error("MQTTBridge: error during disconnect: %s", exc)
        finally:
            self._connected = False
            self._client = None

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_presence(self, user_name: str, is_present: bool) -> None:
        """Publish a presence event for a specific user.

        The message is published to
        ``<topic_prefix>/presence/<user_name>`` with a JSON payload
        containing the user name, presence flag, and an ISO-8601
        timestamp.

        Args:
            user_name: Name of the person whose presence changed.
            is_present: ``True`` if the person is now present.
        """
        payload = {
            "user": user_name,
            "present": is_present,
        }
        topic = f"{self.topic_prefix}/presence/{user_name}"
        self._publish(topic, payload)

    def publish_away(self) -> None:
        """Publish an all-away status event.

        Sent to ``<topic_prefix>/presence/status`` with a JSON payload
        indicating that no known persons are present.
        """
        payload = {"all_away": True}
        topic = f"{self.topic_prefix}/presence/status"
        self._publish(topic, payload)

    def publish_status(self, status_dict: Dict[str, Any]) -> None:
        """Publish a generic status dictionary.

        The message is sent to ``<topic_prefix>/status``.

        Args:
            status_dict: Arbitrary dictionary to serialise as JSON.
        """
        topic = f"{self.topic_prefix}/status"
        self._publish(topic, status_dict)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether the bridge is currently connected to the broker."""
        return self._connected

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Serialise *payload* as JSON and publish to *topic*."""
        if not self._connected or self._client is None:
            logger.debug("MQTTBridge: not connected -- dropping message to %s", topic)
            return

        try:
            from datetime import datetime

            payload["timestamp"] = datetime.now().isoformat()
            body = json.dumps(payload, ensure_ascii=False)
            result = self._client.publish(topic, body, qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning("MQTTBridge: publish to %s failed (rc=%d)", topic, result.rc)
            else:
                logger.debug("MQTTBridge: published to %s", topic)
        except Exception as exc:
            logger.error("MQTTBridge: error publishing to %s: %s", topic, exc)

    def _on_connect(self, client: Any, userdata: Any, flags: dict, rc: int) -> None:
        """Callback invoked when the broker acknowledges the connection."""
        if rc == 0:
            self._connected = True
            logger.info("MQTTBridge: connected to %s:%d", self.broker, self.port)
        else:
            self._connected = False
            logger.error("MQTTBridge: connection refused (rc=%d)", rc)

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        """Callback invoked when the connection is lost."""
        self._connected = False
        if rc == 0:
            logger.info("MQTTBridge: cleanly disconnected")
        else:
            logger.warning("MQTTBridge: unexpected disconnect (rc=%d)", rc)
