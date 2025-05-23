#!/usr/bin/env python3
"""
Kasa Smart Plug Monitor
Monitors a Kasa smart plug and sends email alerts when it's been off for too long.
"""

import asyncio
import smtplib
import time
import logging
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from kasa import SmartPlug
import json
import os

# Configuration
CONFIG_FILE = "kasa_config.json"

# Default configuration
DEFAULT_CONFIG = {
    "plug_ip": "192.168.1.100",  # Replace with your plug's IP
    "check_interval": 60,  # Check every 60 seconds
    "alert_threshold": 300,  # Alert if off for 5 minutes (300 seconds)
    "email": {
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "sender_email": "your_email@gmail.com",
        "sender_password": "your_app_password",  # Use app password for Gmail
        "recipient_email": "recipient@gmail.com"
    }
}


class KasaMonitor:
    def __init__(self, config_file=CONFIG_FILE):
        self.config = self.load_config(config_file)
        self.plug = SmartPlug(self.config["plug_ip"])
        self.off_since = None
        self.alert_sent = False
        self.setup_logging()

    def load_config(self, config_file):
        """Load configuration from JSON file or create default."""
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                return json.load(f)
        else:
            # Create default config file
            with open(config_file, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            print(f"Created default config file: {config_file}")
            print("Please edit the configuration file with your settings.")
            return DEFAULT_CONFIG

    def setup_logging(self):
        """Setup logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('kasa_monitor.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    async def get_plug_state(self):
        """Get the current state of the smart plug."""
        try:
            await self.plug.update()
            return self.plug.is_on
        except Exception as e:
            self.logger.error(f"Error getting plug state: {e}")
            return None

    def send_email_alert(self, minutes_off):
        """Send email alert when plug has been off too long."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config["email"]["sender_email"]
            msg['To'] = self.config["email"]["recipient_email"]
            msg['Subject'] = "Electric Fence - Device Off"

            body = f"""
            Alert: Your Electric Fence smart plug has been turned off for {minutes_off:.1f} minutes.

            Plug IP: {self.config["plug_ip"]}
            Time detected off: {self.off_since.strftime('%Y-%m-%d %H:%M:%S')}
            Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

            Please check your device.
            """

            msg.attach(MIMEText(body, 'plain'))

            return self._send_email(msg)

        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")
            return False

    def send_recovery_email(self, total_downtime_minutes):
        """Send email alert when plug turns back on after being off."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config["email"]["sender_email"]
            msg['To'] = self.config["email"]["recipient_email"]
            msg['Subject'] = "Electric Fence - Device Back Online"

            body = f"""
            Good news: Your Electric Fence smart plug is back online!

            Plug IP: {self.config["plug_ip"]}
            Time went offline: {self.off_since.strftime('%Y-%m-%d %H:%M:%S')}
            Time back online: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            Total downtime: {total_downtime_minutes:.1f} minutes

            Your electric fence is now operational again.
            """

            msg.attach(MIMEText(body, 'plain'))

            return self._send_email(msg)

        except Exception as e:
            self.logger.error(f"Failed to send recovery email: {e}")
            return False

    def _send_email(self, msg):
        """Helper method to send email."""
        try:
            # Connect to SMTP server
            server = smtplib.SMTP(
                self.config["email"]["smtp_server"],
                self.config["email"]["smtp_port"]
            )
            server.starttls()
            server.login(
                self.config["email"]["sender_email"],
                self.config["email"]["sender_password"]
            )

            # Send email
            text = msg.as_string()
            server.sendmail(
                self.config["email"]["sender_email"],
                self.config["email"]["recipient_email"],
                text
            )
            server.quit()

            return True

        except Exception as e:
            self.logger.error(f"Failed to send email: {e}")
            return False

    async def monitor_loop(self):
        """Main monitoring loop."""
        self.logger.info("Starting Kasa smart plug monitor...")
        self.logger.info(f"Monitoring plug at {self.config['plug_ip']}")
        self.logger.info(f"Check interval: {self.config['check_interval']} seconds")
        self.logger.info(f"Alert threshold: {self.config['alert_threshold']} seconds")

        while True:
            try:
                # Get current plug state
                is_on = await self.get_plug_state()

                if is_on is None:
                    self.logger.warning("Could not determine plug state")
                elif is_on:
                    # Plug is on
                    if self.off_since:
                        # Calculate total downtime
                        total_downtime = (datetime.now() - self.off_since).total_seconds() / 60

                        # Send recovery email if we previously sent an alert
                        if self.alert_sent:
                            if self.send_recovery_email(total_downtime):
                                self.logger.info(f"Recovery email sent - plug was off for {total_downtime:.1f} minutes")

                        self.logger.info(f"Plug turned back on after {total_downtime:.1f} minutes")
                        self.off_since = None
                        self.alert_sent = False
                else:
                    # Plug is off
                    now = datetime.now()

                    if self.off_since is None:
                        # Just turned off
                        self.off_since = now
                        self.logger.info("Plug turned off")
                    else:
                        # Has been off for some time
                        time_off = (now - self.off_since).total_seconds()
                        minutes_off = time_off / 60

                        self.logger.info(f"Plug has been off for {minutes_off:.1f} minutes")

                        # Check if we should send alert
                        if time_off >= self.config["alert_threshold"] and not self.alert_sent:
                            if self.send_email_alert(minutes_off):
                                self.alert_sent = True
                                self.logger.info(f"Alert email sent - plug off for {minutes_off:.1f} minutes")

                # Wait before next check
                await asyncio.sleep(self.config["check_interval"])

            except KeyboardInterrupt:
                self.logger.info("Monitor stopped by user")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in monitor loop: {e}")
                await asyncio.sleep(self.config["check_interval"])


async def main():
    """Main function to run the monitor."""
    monitor = KasaMonitor()
    await monitor.monitor_loop()


if __name__ == "__main__":
    asyncio.run(main())