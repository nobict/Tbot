import pytest
from bot import get_file_name
from pyrogram.types import Message, Video, Audio, Document, Photo

@pytest.mark.parametrize("message, expected", [
    (pytest.lazy_fixture('video_message'), "video_test_video.mp4"),
    (pytest.lazy_fixture('audio_message'), "audio_test_audio.mp3"),
    (pytest.lazy_fixture('document_message'), "document_test_document.pdf"),
    (pytest.lazy_fixture('photo_message'), "photo_test_photo.jpg"),
])
def test_get_file_name(message, expected):
    assert get_file_name(message) == expected

# Fixtures for test data
@pytest.fixture
def video_message():
    return Message(
        video=Video(
            file_id="test_video",
            file_name="test video.mp4",
            mime_type="video/mp4"
        ),
        message_id=1
    )

@pytest.fixture
def audio_message():
    return Message(
        audio=Audio(
            file_id="test_audio",
            file_name="test audio.mp3",
            mime_type="audio/mpeg"
        ),
        message_id=2
    )

@pytest.fixture
def document_message():
    return Message(
        document=Document(
            file_id="test_document",
            file_name="test document.pdf",
            mime_type="application/pdf"
        ),
        message_id=3
    )

@pytest.fixture
def photo_message():
    return Message(
        photo=Photo(
            file_id="test_photo",
            file_unique_id="test_photo_unique_id",
            file_size=1024,
            date=1234567890
        ),
        message_id=4
    )