"""Tests for the ADB adapter."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from android_device_mcp.adapters.adb import ADBAdapter, ADBError, CommandResult


class TestADBAdapter:
    """Tests for ADBAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create an ADB adapter with mocked binary path."""
        with patch.object(ADBAdapter, '_find_adb', return_value='/usr/bin/adb'):
            return ADBAdapter()

    @pytest.mark.asyncio
    async def test_run_success(self, adapter):
        """Test successful command execution."""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b'device123\tdevice\n', b'')
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await adapter.run('devices')

            assert result.success
            assert 'device123' in result.stdout

    @pytest.mark.asyncio
    async def test_run_failure(self, adapter):
        """Test failed command execution."""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate.return_value = (b'', b'error: no devices')
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            result = await adapter.run('shell', 'test')

            assert not result.success
            assert 'error' in result.stderr

    @pytest.mark.asyncio
    async def test_get_screen_size(self, adapter):
        """Test screen size parsing."""
        with patch.object(adapter, 'shell') as mock_shell:
            mock_shell.return_value = CommandResult(
                stdout='Physical size: 1080x2340\n',
                stderr='',
                exit_code=0
            )

            result = await adapter.get_screen_size()

            assert result['width'] == 1080
            assert result['height'] == 2340

    @pytest.mark.asyncio
    async def test_get_device_info(self, adapter):
        """Test device info retrieval."""
        with patch.object(adapter, 'shell') as mock_shell:
            mock_shell.side_effect = [
                CommandResult(stdout='Pixel 6\n', stderr='', exit_code=0),
                CommandResult(stdout='Google\n', stderr='', exit_code=0),
                CommandResult(stdout='13\n', stderr='', exit_code=0),
                CommandResult(stdout='33\n', stderr='', exit_code=0),
                CommandResult(stdout='oriole\n', stderr='', exit_code=0),
                CommandResult(stdout='ABC123\n', stderr='', exit_code=0),
            ]
            with patch.object(adapter, 'get_screen_size') as mock_screen:
                mock_screen.return_value = {'width': 1080, 'height': 2400}

                result = await adapter.get_device_info()

                assert result['model'] == 'Pixel 6'
                assert result['manufacturer'] == 'Google'
                assert result['api_level'] == 33

    def test_key_codes(self, adapter):
        """Test key code mapping."""
        assert adapter.KEY_CODES['back'] == 4
        assert adapter.KEY_CODES['home'] == 3
        assert adapter.KEY_CODES['enter'] == 66

    @pytest.mark.asyncio
    async def test_validate_package_name(self, adapter):
        """Test package name validation."""
        # Valid package names should work
        with patch.object(adapter, 'shell') as mock_shell:
            mock_shell.return_value = CommandResult(stdout='', stderr='', exit_code=0)
            result = await adapter.stop_app('com.example.app')
            assert result.success

        # Invalid package names should raise error
        with pytest.raises(ADBError):
            await adapter.stop_app('invalid;rm -rf /')

    @pytest.mark.asyncio
    async def test_install_apk_validates_path(self, adapter):
        """Test APK path validation."""
        # Non-existent file should fail
        with pytest.raises(ADBError):
            await adapter.install_apk('/nonexistent/path.apk')


class TestCommandResult:
    """Tests for CommandResult."""

    def test_success_true_when_exit_code_zero(self):
        """Test success property."""
        result = CommandResult(stdout='ok', stderr='', exit_code=0)
        assert result.success

    def test_success_false_when_exit_code_nonzero(self):
        """Test failure detection."""
        result = CommandResult(stdout='', stderr='error', exit_code=1)
        assert not result.success
