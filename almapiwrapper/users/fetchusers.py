import almapiwrapper.users as userslib
from typing import List, Optional, Literal, Dict
from ..apikeys import ApiKeys
from ..record import JsonData
import requests
import logging


def fetch_users(q: str, zone: str, env: Optional[Literal['P', 'S']] = 'P') -> List[userslib.User]:
    """Search users in IZ according to a request

    :param q: request in API syntax. "user_group~06" will search every linked account
    :param zone: code of the IZ, NZ or "all" for all IZs NZ excepted.
    :param env: "P" for production, "S" for sandbox. Default is production
    :return: list of :class:`almapiwrapper.users.User`
    """
    error = False
    users = []
    list_iz = ApiKeys().get_iz_codes() if zone == 'all' else [zone]
    for z in list_iz:

        # Interrupt in case of any error
        if error is True:
            break

        # Init counters
        offset = 0
        nb_total_records = 0

        # Handle offset if more than 100 results are available
        while offset == 0 or offset < nb_total_records:

            # Make request
            r = requests.get(f'{userslib.User.api_base_url}',
                             params={'q': q, 'limit': 100, 'offset': offset},
                             headers=_get_headers(z, 'RW', env))

            # Check result
            if r.ok is True:
                users_list = JsonData(r.json())
                nb_total_records = int(users_list.content['total_record_count'])

                if 'user' in users_list.content:
                    users += [userslib.User(user['primary_id'], z, env) for user in users_list.content['user']]
                    nb_users = len(users_list.content['user'])
                else:
                    nb_users = 0

                logging.info(f'fetch_users({q}, {z}, {env}): '
                             f'{offset + nb_users} / '
                             f'{nb_total_records} users data available')
                offset += 100
            else:
                _handle_error(q, r, f'unable to fetch data', z, env)
                error = True
                break

    return users


def fetch_user_in_all_iz(primary_id: str, env: Optional[Literal['P', 'S']] = 'P') -> List[userslib.User]:
    """Fetch by primary ID a user in all IZ

    :param primary_id: primary ID of the user to search across all IZs
    :param env: "P" for production, "S" for sandbox. Default is production
    :return: list of :class:`almapiwrapper.users.User`
    """

    list_iz = ApiKeys().get_iz_codes()
    users = []
    for iz in list_iz:
        user = userslib.User(primary_id, iz, env)

        _ = user.data

        if user.error is False:
            users.append(user)

    return users


def _handle_error(q: str, r: requests.models.Response, msg: str, zone: str, env: str):
    """Set the record error attribute to True and write the logs about the error

    :param r: request response of the api
    :param msg: context message of the error
    :return: None
    """
    json_data = r.json()
    error_message = json_data['errorList']['error'][0]['errorMessage']

    logging.error(f'fetch_users({q}, {zone}, {env}) - {r.status_code}: '
                  f'{msg} / {error_message}')


def _get_headers(zone: Optional[str],
                 rights: Literal['R', 'RW'] = 'RW',
                 env: Optional[Literal['P', 'S']] = 'P') -> Dict:
    """
    Build the headers for the API calls.
    :param zone: optional, if indicated allow to make the query in an other IZ
    que celle de l'objet courant
    :param env: environment of the api call: 'P' for production, 'S' for sandbox
    :return: dict with the header
    """

    # Build header dict
    return {'content-type': f'application/json',
            'accept': f'application/json',
            'Authorization': 'apikey ' + ApiKeys().get_key(zone, 'Users', rights, env)}


if __name__ == "__main__":
    pass
