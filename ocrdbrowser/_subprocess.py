from __future__ import annotations

import asyncio
import logging
import os
import signal
from shutil import which

from ._browser import OcrdBrowser, OcrdBrowserClient
from ._client import HttpBrowserClient
from ._port import NoPortsAvailableError

BROADWAY_BASE_PORT = 8080


class SubProcessOcrdBrowser:
    def __init__(
        self, owner: str, workspace: str, address: str, process_id: str
    ) -> None:
        self._owner = owner
        self._workspace = workspace
        self._address = address
        self._process_id = process_id

    def process_id(self) -> str:
        return self._process_id

    def address(self) -> str:
        return self._address

    def workspace(self) -> str:
        return self._workspace

    def owner(self) -> str:
        return self._owner

    async def stop(self) -> None:
        try:
            os.kill(int(self._process_id), signal.SIGKILL)
        except ProcessLookupError:
            logging.warning(f"Could not find process with ID {self._process_id}")

    def client(self) -> OcrdBrowserClient:
        return HttpBrowserClient(self.address())


class SubProcessOcrdBrowserFactory:
    def __init__(self, available_ports: set[int]) -> None:
        self._available_ports = available_ports

    async def __call__(self, owner: str, workspace_path: str) -> OcrdBrowser:
        for port in self._available_ports:
            address = f"http://localhost:{port}"
            process = await self.start_browser(workspace_path, port)

            await asyncio.sleep(1)
            if process.returncode is None:
                return SubProcessOcrdBrowser(
                    owner, workspace_path, address, str(process.pid)
                )
            else:
                continue

        raise NoPortsAvailableError()

    async def start_browser(
        self, workspace: str, port: int
    ) -> asyncio.subprocess.Process:
        browse_ocrd = which("browse-ocrd")
        if not browse_ocrd:
            raise FileNotFoundError("Could not find browse-ocrd executable")

        # broadwayd (which uses WebSockets) only allows a single client at a time
        # (disconnecting concurrent connections), hence we must start a new daemon
        # for each new browser session
        # broadwayd starts counting virtual X displays from port 8080 as :0
        displayport = str(port - BROADWAY_BASE_PORT)
        environment = dict(os.environ)
        environment["GDK_BACKEND"] = "broadway"
        environment["BROADWAY_DISPLAY"] = ":" + displayport

        try:
            return await asyncio.create_subprocess_shell(
                " ".join(
                    [
                        "broadwayd",
                        ":" + displayport + " &",
                        browse_ocrd,
                        workspace + "/mets.xml ;",
                        "kill $!",
                    ]
                ),
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as err:
            logging.error(
                f"Failed to launch broadway at {displayport} (real port {port})"
            )
            raise err
