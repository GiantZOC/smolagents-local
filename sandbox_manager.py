import docker
import os
from typing import Optional, Dict

class DockerSandbox:
    def __init__(
        self, 
        enable_phoenix: bool = True,
        phoenix_endpoint: str = None,
        network_name: str = "smolagents_smolagents-network"
    ):
        """
        Initialize a Docker sandbox with optional Phoenix telemetry support.
        
        Args:
            enable_phoenix: Enable Phoenix OpenTelemetry integration
            phoenix_endpoint: Phoenix collector endpoint (default: http://phoenix:4317)
            network_name: Docker network name to join (for Phoenix connectivity)
        """
        self.client = docker.from_env()
        self.container = None
        self.enable_phoenix = enable_phoenix
        self.phoenix_endpoint = phoenix_endpoint or "http://phoenix:4317"
        self.network_name = network_name

    def create_container(self):
        try:
            image, build_logs = self.client.images.build(
                path=".",
                tag="agent-sandbox",
                rm=True,
                forcerm=True,
                buildargs={},
                # decode=True
            )
        except docker.errors.BuildError as e:
            print("Build error logs:")
            for log in e.build_log:
                if 'stream' in log:
                    print(log['stream'].strip())
            raise

        # Prepare environment variables
        env_vars = {
            "HF_TOKEN": os.getenv("HF_TOKEN", "")
        }
        
        # Add Phoenix configuration if enabled
        if self.enable_phoenix:
            env_vars.update({
                "OTEL_EXPORTER_OTLP_ENDPOINT": self.phoenix_endpoint,
                "PHOENIX_COLLECTOR_ENDPOINT": self.phoenix_endpoint.replace(":4317", ":6006"),
                "PHOENIX_WORKING_DIR": "/tmp/phoenix",  # Use /tmp which is writable
            })

        # Determine network mode and extra hosts
        # If Phoenix is enabled, use bridge network to connect to Phoenix container
        # Otherwise, use host network for direct Ollama access
        if self.enable_phoenix:
            network_mode = None  # Will use network specified separately
            extra_hosts = {"host.docker.internal": "host-gateway"}  # For accessing Ollama on host
        else:
            network_mode = "host"
            extra_hosts = None

        # Create container with security constraints
        self.container = self.client.containers.run(
            "agent-sandbox",
            command="tail -f /dev/null",  # Keep container running
            detach=True,
            tty=True,
            mem_limit="512m",
            cpu_quota=50000,
            pids_limit=100,
            security_opt=["no-new-privileges"],
            cap_drop=["ALL"],
            network_mode=network_mode,
            environment=env_vars,
            extra_hosts=extra_hosts,
        )
        
        # Connect to Phoenix network if enabled
        if self.enable_phoenix:
            try:
                network = self.client.networks.get(self.network_name)
                network.connect(self.container)
                print(f"✓ Connected sandbox to Phoenix network: {self.network_name}")
            except docker.errors.NotFound:
                print(f"⚠ Warning: Network '{self.network_name}' not found.")
                print("  Phoenix telemetry may not work. Make sure Phoenix is running:")
                print("  docker-compose up -d phoenix")
            except Exception as e:
                print(f"⚠ Warning: Could not connect to network: {e}")

    def run_code(self, code: str, setup_phoenix: bool = None) -> Optional[str]:
        """
        Run Python code in the sandbox container.
        
        Args:
            code: Python code to execute
            setup_phoenix: Override Phoenix setup (default: use instance setting)
            
        Returns:
            Output from code execution
        """
        if not self.container:
            self.create_container()

        # Determine if we should set up Phoenix for this run
        use_phoenix = setup_phoenix if setup_phoenix is not None else self.enable_phoenix
        
        # Prepend Phoenix instrumentation if enabled
        if use_phoenix:
            phoenix_setup = '''
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

# Set up Phoenix telemetry
try:
    from phoenix.otel import register
    from openinference.instrumentation.smolagents import SmolagentsInstrumentor
    
    register()
    SmolagentsInstrumentor().instrument()
    print("✓ Phoenix telemetry enabled")
except Exception as e:
    print(f"⚠ Phoenix setup failed: {e}")

'''
            code = phoenix_setup + code

        # Execute code in container
        exec_result = self.container.exec_run(
            cmd=["python", "-c", code],
            user="nobody"
        )

        # Collect all output
        return exec_result.output.decode() if exec_result.output else None


    def cleanup(self):
        if self.container:
            try:
                self.container.stop()
            except docker.errors.NotFound:
                # Container already removed, this is expected
                pass
            except Exception as e:
                print(f"Error during cleanup: {e}")
            finally:
                self.container = None  # Clear the reference
