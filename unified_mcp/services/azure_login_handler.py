"""Azure Login Handler for device code authentication."""

import asyncio
import logging
import os
import re
from typing import List, Optional


class AzureLoginHandler:
    """Handler for Azure CLI login with device code authentication."""

    def __init__(self) -> None:
        """Initialize Azure login handler."""
        self.logger = logging.getLogger(__name__)
        self.current_process: Optional[asyncio.subprocess.Process] = None
        self.logger.info("AzureLoginHandler initialized")

    async def handle_az_login_command(self, command: str) -> str:
        """Handle Azure CLI login with device code authentication."""
        self.logger.info(f"Handling 'az login' command: {command}")

        # Always force device code authentication for Docker containers
        # Remove any existing authentication flags that might conflict
        command = re.sub(r'--use-device-code\b', '', command)
        command = re.sub(r'--service-principal\b', '', command)
        command = re.sub(r'--username\b\s+\S+', '', command)
        command = re.sub(r'--password\b\s+\S+', '', command)
        command = re.sub(r'--tenant\b\s+\S+', '', command)
        
        # Add device code flag
        command = command.strip() + " --use-device-code"
        
        self.logger.info(f"Modified command to use device code: {command}")

        try:
            # Cancel previous login process if running
            if self.current_process and not self.current_process.returncode:
                self.logger.info("Cancelling previous 'az login' process")
                self.current_process.terminate()
                try:
                    await asyncio.wait_for(self.current_process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.logger.warning(
                        "Previous login process did not terminate gracefully"
                    )
                    self.current_process.kill()

            # Start new login process with unbuffered output
            self.current_process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Redirect stderr to stdout
                stdin=asyncio.subprocess.PIPE,
                shell=True,
                env={**dict(os.environ), "PYTHONUNBUFFERED": "1"}  # Force unbuffered output
            )

            # Handle login process in background and get result
            result = await self._handle_login_background(self.current_process)

            # Clean up process reference
            self.current_process = None

            return result

        except Exception as e:
            self.logger.error(f"Error running 'az login' command: {e}")
            # Clean up process reference on error
            self.current_process = None
            return f"Error: Failed to start login process - {str(e)}"

    async def _handle_login_background(
        self, process: asyncio.subprocess.Process
    ) -> str:
        """Handle login process and return device code info immediately."""
        try:
            self.logger.info("Reading device code information from az login")

            device_code_info = []
            all_output = []
            
            # Read from stdout (stderr is redirected to stdout)
            if process.stdout:
                try:
                    # Read lines one by one with timeout
                    for _ in range(30):  # Read up to 30 lines
                        try:
                            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                            if not line:
                                break
                            
                            decoded_line = line.decode("utf-8").strip()
                            if decoded_line:
                                all_output.append(decoded_line)
                                self.logger.info(f"Azure CLI output: {decoded_line}")
                                
                                # Look for device code information
                                if any(keyword in decoded_line.lower() for keyword in 
                                      ["device", "code", "browser", "authenticate", "https://", "to sign in", "microsoft.com"]):
                                    device_code_info.append(decoded_line)
                                
                                # If we have device code info, check if we have enough
                                if device_code_info and (len(device_code_info) >= 2 or "https://" in decoded_line):
                                    result = "\n".join(device_code_info)
                                    self.logger.info("Found device code info, returning immediately")
                                    
                                    # Continue process in background without blocking
                                    asyncio.create_task(self._continue_login_background(process))
                                    
                                    return result
                                    
                        except asyncio.TimeoutError:
                            # Check if we have any device code info collected so far
                            if device_code_info:
                                result = "\n".join(device_code_info)
                                self.logger.info("Timeout but have device code info, returning it")
                                asyncio.create_task(self._continue_login_background(process))
                                return result
                            continue  # Keep trying to read more lines
                            
                except Exception as e:
                    self.logger.error(f"Error reading stdout: {e}")
                    
            # If we didn't get device code info, return what we have
            if device_code_info:
                return "\n".join(device_code_info)
            elif all_output:
                return "\n".join(all_output)
            else:
                return "Device code authentication started. Please check Azure CLI output."

        except Exception as e:
            self.logger.error(f"Error reading device code info: {e}")
            return f"Error: {str(e)}"
    
    async def _continue_login_background(self, process: asyncio.subprocess.Process) -> None:
        """Continue the login process in the background."""
        try:
            self.logger.info("Continuing login process in background")
            
            # Read remaining output from both streams
            async def read_remaining(stream, stream_name):
                if stream:
                    try:
                        async for line in stream:
                            decoded_line = line.decode("utf-8").strip()
                            if decoded_line:
                                self.logger.debug(f"Background {stream_name}: {decoded_line}")
                    except Exception as e:
                        self.logger.debug(f"Error reading background {stream_name}: {e}")
            
            # Read from both streams concurrently
            await asyncio.gather(
                read_remaining(process.stdout, "stdout"),
                read_remaining(process.stderr, "stderr"),
                return_exceptions=True
            )
            
            # Wait for completion
            return_code = await process.wait()
            
            if return_code == 0:
                self.logger.info("Background login completed successfully")
            else:
                self.logger.warning(f"Background login failed with code: {return_code}")
                
        except Exception as e:
            self.logger.error(f"Error in background login continuation: {e}")

    async def _read_lines(self, stream: asyncio.StreamReader) -> List[str]:
        """Asynchronously read lines from stream."""
        if not stream:
            return []

        lines = []
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                try:
                    decoded_line = line.decode("utf-8").strip()
                    if decoded_line:  # Skip empty lines
                        lines.append(decoded_line)
                        self.logger.debug(f"Read line: {decoded_line}")
                except UnicodeDecodeError as e:
                    self.logger.warning(f"Could not decode line: {e}")
                    # Try with error handling
                    try:
                        decoded_line = line.decode("utf-8", errors="replace").strip()
                        if decoded_line:
                            lines.append(decoded_line)
                    except Exception:
                        pass  # Skip lines that can't be decoded
        except Exception as e:
            self.logger.error(f"Error reading stream: {e}")

        return lines 