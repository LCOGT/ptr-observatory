from ocs_archive.input.file import File, DataFile
from ocs_archive.settings import settings

class PtrBaseFileClass(DataFile):
    def __init__(self, open_file: File, file_metadata: dict = None, blacklist_headers: tuple = settings.HEADER_BLACKLIST, required_headers: tuple = settings.REQUIRED_HEADERS):
        """Loads in file headers, then does some automatic cleanup and normalization of values."""
        super().__init__(open_file, file_metadata, blacklist_headers, required_headers)
        self._remove_blacklist_headers(blacklist_headers)
        self._normalize_related_frames()

    def _remove_blacklist_headers(self, blacklist_headers: tuple):
        if '' not in blacklist_headers:
            # Always remove the empty string header since it causes issues
            self.header_data.remove_header('')
        for header in self.blacklist_headers:
            self.header_data.remove_header(header)

    def _normalize_related_frames(self):
        related_frame_keys = self.header_data.get_related_frame_keys()
        headers = self.header_data.get_headers()
        for key in related_frame_keys:
            filename = headers.get(key)
            if filename and filename != 'N/A':
                basename, extension = File.get_basename_and_extension(filename)
                if extension:
                    # Remove any extensions for the related frames, since the archive expects that
                    self.header_data.update_headers({key: basename})