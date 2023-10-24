from ocs_archive.input.file import File, DataFile, FileSpecificationException
from ocs_archive.input.headerdata import HeaderData
from ocs_archive.settings import settings

class PtrHeaderData(HeaderData):
    def get_archive_frame_data(self):
        archive_frame_data = super().get_archive_frame_data()
        # add additional metadata as neeeded
        archive_frame_data['user_id'] = self.get_user_id()
        return archive_frame_data
    
    def get_user_id(self):
        return self.get_headers().get('USERID', '')


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

    def _create_header_data(self, file_metadata: dict):
        if self._is_valid_file_metadata(file_metadata):
            self.header_data = PtrHeaderData(file_metadata)
            return
        # Missing one or more required headers in the input file_metadata
        raise FileSpecificationException('Could not find required keywords in headers!')
