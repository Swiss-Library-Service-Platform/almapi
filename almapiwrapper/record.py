import abc
from .apikeys import ApiKeys
from typing import Optional, Callable, ClassVar, Literal, Dict, Union
import logging
import json
from lxml import etree
import os
import requests


def check_error(fn: Callable) -> Callable:
    """Prevents operation if the record is containing an error

    :param fn: method that should not to be executed in case of error
    :return: wrapper function
    """
    def wrapper(*args, **kwargs):
        """Wrapper function

        """
        rec = args[0]
        if rec.error is False and rec.data is not None:
            rec = fn(*args, **kwargs)
        else:
            logging.error(f'{repr(rec)}: due to error to the record, process "{fn.__name__}" skipped.')
        return rec

    wrapper.__doc__ = fn.__doc__

    return wrapper


class Record(metaclass=abc.ABCMeta):
    """
    This class is representing entities like bibliographic records, items or holdings.
    It contains common methods to all entities.
    """
    # Used to get API keys
    k: ClassVar[ApiKeys] = ApiKeys()

    # Api urls
    api_base_url: ClassVar[str] = 'https://api-eu.hosted.exlibrisgroup.com/almaws/v1'

    # Using this parser avoids some problems with 'tostring' method
    parser: ClassVar[etree.XMLParser] = etree.XMLParser(remove_blank_text=True)

    def __init__(self, zone: str,
                 env: Literal['P', 'S'] = 'P',
                 data: Optional['JsonData'] = None) -> None:
        """
        Abstract constructor, all entities have at least a zone and an environment.
        :param zone: zone of the record
        :param env: environment of the entity: 'P' for production and 'S' for sandbox
        """
        self.error = False
        self.zone = zone
        self.env = env
        self.area = None
        self._data = data

    @abc.abstractmethod
    def _fetch_data(self) -> None:
        """Abstract method. This method is different according to the type of record"""
        return None

    @property
    def data(self) -> Optional[Union[Dict, etree.Element]]:
        """
        Property that get xml data with API call. If not available, make an api call
        :return: xml data
        """
        if self._data is None and self.error is False:
            self.data = self._fetch_data()

        if self._data is not None:
            return self._data.content

    @data.setter
    def data(self, data: Union['JsonData', 'XmlData']) -> None:
        """
        Property used to set xml data of an holding
        :param data: dictionary with holding xml data
        :return: None
        """
        self._data = data

    def __str__(self) -> str:
        """
        return content of data attribut as a string
        :return: string data
        """
        if self.data is not None:
            return str(self._data)
        else:
            return ''

    def __bytes__(self):
        """
        :return: bytes data
        """
        if self.data is not None:
            return bytes(self._data)
        else:
            return b''

    def _save_from_path(self, filepath: str) -> None:
        """
        Save a record in the 'records' folder. Versioning is supported. A suffix is added to the file path.
        :param filepath: initial path of the saved record
        :return: None
        """
        # Fetch directory
        directory = os.path.dirname(filepath)

        # Create the directory if it doesn't exist
        os.makedirs(directory, exist_ok=True)

        # Add a suffix _xx to the file name before extension
        filename = os.path.basename(filepath)
        base_filename, extension = filename.rsplit('.', 1)
        files = os.listdir(directory)
        version = str(len([f for f in files if base_filename in f]) + 1).zfill(2)

        # Build the final path
        final_path = os.path.join(directory, f'{base_filename}_{version}.{extension}')

        # Write the file
        with open(final_path, 'w') as f:
            f.write(str(self))

        logging.info(f'{repr(self)}: record saved: {final_path}')

    def _get_headers(self,
                     data_format: Literal['json', 'xml'] = 'json',
                     zone: Optional[str] = None,
                     rights: Literal['R', 'RW'] = 'RW',
                     env: Optional[Literal['P', 'S']] = None) -> Dict:
        """
        Build the headers for the API calls.
        :param data_format: "json" ou "xml" en fonction du format souhaité
        :param zone: optional, if indicated allow to make the query in an other IZ
        que celle de l'objet courant
        :param env: environment of the api call: 'P' for production, 'S' for sandbox
        :return: dict with the header
        """

        # If values are not provided, fetch values of the current entity
        if zone is None:
            zone = self.zone
        if env is None:
            env = self.env

        # Build header dict
        return {'content-type': f'application/{data_format}',
                'accept': f'application/{data_format}',
                'Authorization': 'apikey ' + self.k.get_key(zone, self.area, rights, env)}

    def _handle_error(self, r: requests.models.Response, msg: str):
        """
        Set the record error attribute to True and write the logs about the error
        :param r: request response of the api
        :param msg: context message of the error
        :return: None
        """
        if 'json' in r.headers['Content-Type']:
            json_data = r.json()
            error_message = json_data['errorList']['error'][0]['errorMessage']
        else:
            xml = etree.fromstring(r.content, parser=self.parser)
            error_message = xml.find('.//{http://com/exlibris/urm/general/xmlbeans}errorMessage').text
        logging.error(f'{repr(self)} - {r.status_code}: '
                      f'{msg} / {error_message}')
        self.error = True


class XmlData:

    # Using this parser avoids some problems with 'tostring' method
    parser: ClassVar[etree.XMLParser] = etree.XMLParser(remove_blank_text=True)

    def __init__(self, content: etree.Element):
        self.content = content

    def __str__(self):
        return etree.tostring(self.content, pretty_print=True).decode()


class JsonData:
    """
    Simple class representing json data. Only very general methods are described here.
    Method to create, update or delete the data are at the record level.

    :ivar content: json content of the object

    :Example:

    >>> from almapiwrapper.record import JsonData
    >>> data = JsonData(filepath='path_to_some_json_file')
    >>> print(data)

    Will pretty print the json content.

    Data can be changed in the `content` attribute.
    """
    def __init__(self, content: Optional[Dict] = None, filepath: Optional[str] = None):
        self.content = content
        if filepath is not None:
            self.content = self._read_file(filepath)

    def __str__(self):
        return json.dumps(self.content, indent=2)

    def __bytes__(self):
        data_str = json.dumps(self.content)
        return bytes(data_str, 'utf-8)')

    @staticmethod
    def _read_file(filepath: str) -> Optional[Dict]:
        """
        Read json data file from disk
        :param filepath: patrh to the data file
        :return: json data
        """
        try:
            f = open(filepath, 'rb')
        except FileNotFoundError:
            logging.error(f'File not found: {filepath}')
            return

        try:
            data = json.load(f)
            logging.info(f'Json data file read: {filepath}')
        except ValueError:
            logging.error(f'Failed to read json: {filepath}')
            data = None
        finally:
            f.close()

        return data