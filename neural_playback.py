"""Play local neural PCM through the existing Discord virtual microphone."""
import subprocess
import tempfile

from media_tools import ffmpeg_executable


def play_neural_audio(engine, text, voice, speed, sink, cancel_event, on_status, on_player):
    """Consume 48 kHz s16le mono chunks without writing a complete audio file."""
    if cancel_event.is_set():
        return
    processes = []
    stream = None
    decoder = None
    factor = speed / 155
    if not 0.5 <= factor <= 3:
        raise ValueError('Offline speech speed is out of range')
    filters = []
    while factor > 2:
        filters.append('atempo=2')
        factor /= 2
    if factor != 1:
        filters.append(f'atempo={factor:.8f}')
    with tempfile.TemporaryFile() as decoder_errors, tempfile.TemporaryFile() as player_errors:
        try:
            arguments = [ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                         '-f', 's16le', '-ar', '48000', '-ac', '1',
                         '-probesize', '32', '-analyzeduration', '0', '-i', 'pipe:0']
            if filters:
                arguments += ['-af', ','.join(filters)]
            arguments += ['-f', 's16le', '-c:a', 'pcm_s16le', '-flush_packets', '1', 'pipe:1']
            decoder = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=decoder_errors)
            processes.append(decoder)
            player = subprocess.Popen(
                ['paplay', '--device', sink, '--raw', '--format=s16le',
                 '--rate=48000', '--channels=1', '--latency-msec=40'],
                stdin=decoder.stdout, stdout=subprocess.DEVNULL, stderr=player_errors)
            processes.append(player)
            decoder.stdout.close()
            on_player(player)
            received = False
            stream = engine.stream(text, voice, cancel_event, on_status)
            for data in stream:
                if cancel_event.is_set():
                    return
                if data:
                    decoder.stdin.write(data)
                    decoder.stdin.flush()
                    if not received:
                        on_status('Playing offline AI speech to Discord...')
                    received = True
            if cancel_event.is_set():
                return
            if not received:
                raise RuntimeError('Offline AI model returned no audio. Try another preset voice.')
            decoder.stdin.close()
            for process, label, errors in ((decoder, 'FFmpeg', decoder_errors),
                                           (player, 'Audio playback', player_errors)):
                result = process.wait()
                if result and not cancel_event.is_set():
                    errors.seek(0)
                    raise RuntimeError(label + ' failed: ' + errors.read().decode(errors='replace'))
        finally:
            if stream is not None and hasattr(stream, 'close'):
                stream.close()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            if decoder is not None:
                for pipe in (decoder.stdin, decoder.stdout):
                    if pipe is not None:
                        try:
                            pipe.close()
                        except OSError:
                            pass
            for process in processes:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            on_player(None)
