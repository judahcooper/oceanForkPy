"""Brizo module."""

#  Copyright 2018 Ocean Protocol Foundation
#  SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
import re
from json import JSONDecodeError

from ocean_lib.web3_internal import Web3Helper
from ocean_lib.web3_internal.utils import add_ethereum_prefix_and_hash_msg
from ocean_utils.agreements.service_types import ServiceTypes
from ocean_utils.exceptions import OceanEncryptAssetUrlsError
from ocean_utils.http_requests.requests_session import get_requests_session

from ocean_lib.models.algorithm_metadata import AlgorithmMetadata

logger = logging.getLogger(__name__)


class DataServiceProvider:
    """
    `Brizo` is the name chosen for the asset service provider.

    The main functions available are:
    - consume_service
    - run_compute_service (not implemented yet)

    """
    _http_client = get_requests_session()

    @staticmethod
    def set_http_client(http_client):
        """Set the http client to something other than the default `requests`"""
        DataServiceProvider._http_client = http_client

    @staticmethod
    def encrypt_files_dict(files_dict, encrypt_endpoint, asset_id, account_address, signed_did):
        payload = json.dumps({
            'documentId': asset_id,
            'signature': signed_did,
            'document': json.dumps(files_dict),
            'publisherAddress': account_address
        })

        response = DataServiceProvider._http_client.post(
            encrypt_endpoint, data=payload,
            headers={'content-type': 'application/json'}
        )
        if response and hasattr(response, 'status_code'):
            if response.status_code != 201:
                msg = (f'Encrypt file urls failed at the encryptEndpoint '
                       f'{encrypt_endpoint}, reason {response.text}, status {response.status_code}'
                       )
                logger.error(msg)
                raise OceanEncryptAssetUrlsError(msg)

            logger.info(
                f'Asset urls encrypted successfully, encrypted urls str: {response.text},'
                f' encryptedEndpoint {encrypt_endpoint}')

            return response.json()['encryptedDocument']

    @staticmethod
    def check_service_availability(did, service_endpoint, account, service_id, service_type,
                                   token_address):
        initialize_url = (
            f'{service_endpoint}'
            f'?documentId={did}'
            f'&serviceId={service_id}'
            f'&serviceType={service_type}'
            f'&tokenAddress={token_address}'
            f'&consumerAddress={account.address}'
        )

        logger.info(f'invoke the initialize endpoint with this url: {initialize_url}')
        response = DataServiceProvider._http_client.get(initialize_url, stream=True)
        # The returned json should contain information about the required number of tokens
        # to consume `service_id`. If service is not available there will be an error or
        # the returned json is empty.
        if response.status_code != 200:
            return None

        return response.json()

    @staticmethod
    def download_service(did, service_endpoint, account, files,
                         destination_folder, service_id,
                         token_address, token_transfer_tx_id,
                         index=None):
        """
        Call the provider endpoint to get access to the different files that form the asset.

        :param did: str id of the asset
        :param service_endpoint: Url to consume, str
        :param account: Account instance of the consumer signing this agreement, hex-str
        :param files: List containing the files to be consumed, list
        :param destination_folder: Path, str
        :param service_id: integer the id of the service inside the DDO's service dict
        :param token_address: hex str the data token address associated with this asset/service
        :param token_transfer_tx_id: hex str the transaction hash for the required data token
            transfer (tokens of the same token address above)
        :param index: Index of the document that is going to be downloaded, int
        :return: True if was downloaded, bool
        """
        signature = Web3Helper.sign_hash(
            add_ethereum_prefix_and_hash_msg(did),
            account)

        indexes = range(len(files))
        if index is not None:
            assert isinstance(index, int), logger.error('index has to be an integer.')
            assert index >= 0, logger.error('index has to be 0 or a positive integer.')
            assert index < len(files), logger.error(
                'index can not be bigger than the number of files')
            indexes = [index]

        base_url = (
            f'{service_endpoint}'
            f'?documentId={did}'
            f'&serviceId={service_id}'
            f'&serviceType={ServiceTypes.ASSET_ACCESS}'
            f'&tokenAddress={token_address}'
            f'&transferTxId={token_transfer_tx_id}'
            f'&consumerAddress={account.address}'
            f'&signature={signature}'
        )
        for i in indexes:
            download_url = base_url + f'&fileIndex={i}'
            logger.info(f'invoke consume endpoint with this url: {download_url}')
            response = DataServiceProvider._http_client.get(download_url, stream=True)
            file_name = DataServiceProvider._get_file_name(response)
            DataServiceProvider.write_file(response, destination_folder, file_name or f'file-{i}')

    @staticmethod
    def start_compute_job(agreement_id, service_endpoint, account_address, signature,
                          service_id, token_address, token_transfer_tx_id,
                          algorithm_did=None, algorithm_meta=None, output=None, job_id=None):
        """

        :param agreement_id: Service Agreement Id, hex str
        :param service_endpoint:
        :param account_address: hex str the ethereum address of the consumer executing the compute job
        :param signature: hex str signed message to allow the provider to authorize the consumer
        :param algorithm_did: str -- the asset did (of `algorithm` type) which consist of `did:op:` and
            the assetId hex str (without `0x` prefix)
        :param algorithm_meta: see `OceanCompute.execute`
        :param output: see `OceanCompute.execute`
        :param job_id: str id of compute job that was started and stopped (optional, use it
            here to start a job after it was stopped)

        :return: job_info dict with jobId, status, and other values
        """
        assert algorithm_did or algorithm_meta, 'either an algorithm did or an algorithm meta must be provided.'

        payload = DataServiceProvider._prepare_compute_payload(
            agreement_id,
            account_address,
            signature,
            algorithm_did,
            algorithm_meta,
            output,
            service_id,
            ServiceTypes.CLOUD_COMPUTE,
            token_address,
            token_transfer_tx_id,
            job_id
        )
        logger.info(f'invoke start compute endpoint with this url: {payload}')
        response = DataServiceProvider._http_client.post(
            service_endpoint,
            data=json.dumps(payload),
            headers={'content-type': 'application/json'}
        )
        logger.debug(f'got DataProvider execute response: {response.content} with status-code {response.status_code} ')
        if response.status_code not in (201, 200):
            raise Exception(response.content.decode('utf-8'))

        try:
            job_info = json.loads(response.content.decode('utf-8'))
            if isinstance(job_info, list):
                return job_info[0]
            return job_info

        except KeyError as err:
            logger.error(f'Failed to extract jobId from response: {err}')
            raise KeyError(f'Failed to extract jobId from response: {err}')
        except JSONDecodeError as err:
            logger.error(f'Failed to parse response json: {err}')
            raise

    @staticmethod
    def stop_compute_job(agreement_id, job_id, service_endpoint, account_address, signature):
        """

        :param agreement_id: hex str Service Agreement Id
        :param job_id: str id of compute job that was returned from `start_compute_job`
        :param service_endpoint: str url of the provider service endpoint for compute service
        :param account_address: hex str the ethereum address of the consumer's account
        :param signature: hex str signed message to allow the provider to authorize the consumer

        :return: bool whether the job was stopped successfully
        """
        return DataServiceProvider._send_compute_request(
            'put', agreement_id, job_id, service_endpoint, account_address, signature)

    @staticmethod
    def restart_compute_job(agreement_id, job_id, service_endpoint, account_address, signature):
        """

        :param agreement_id: hex str Service Agreement Id
        :param job_id: str id of compute job that was returned from `start_compute_job`
        :param service_endpoint: str url of the provider service endpoint for compute service
        :param account_address: hex str the ethereum address of the consumer's account
        :param signature: hex str signed message to allow the provider to authorize the consumer

        :return: bool whether the job was restarted successfully
        """
        DataServiceProvider.stop_compute_job(agreement_id, job_id, service_endpoint, account_address, signature)
        return DataServiceProvider.start_compute_job(agreement_id, service_endpoint, account_address, signature, job_id=job_id)

    @staticmethod
    def delete_compute_job(agreement_id, job_id, service_endpoint, account_address, signature):
        """

        :param agreement_id: hex str Service Agreement Id
        :param job_id: str id of compute job that was returned from `start_compute_job`
        :param service_endpoint: str url of the provider service endpoint for compute service
        :param account_address: hex str the ethereum address of the consumer's account
        :param signature: hex str signed message to allow the provider to authorize the consumer

        :return: bool whether the job was deleted successfully
        """
        return DataServiceProvider._send_compute_request(
            'delete', agreement_id, job_id, service_endpoint, account_address, signature)

    @staticmethod
    def compute_job_status(agreement_id, job_id, service_endpoint, account_address, signature):
        """

        :param agreement_id: hex str Service Agreement Id
        :param job_id: str id of compute job that was returned from `start_compute_job`
        :param service_endpoint: str url of the provider service endpoint for compute service
        :param account_address: hex str the ethereum address of the consumer's account
        :param signature: hex str signed message to allow the provider to authorize the consumer

        :return: dict of job_id to status info. When job_id is not provided, this will return
            status for each job_id that exist for the agreement_id
        """
        return DataServiceProvider._send_compute_request(
            'get', agreement_id, job_id, service_endpoint, account_address, signature)

    @staticmethod
    def compute_job_result(agreement_id, job_id, service_endpoint, account_address, signature):
        """

        :param agreement_id: hex str Service Agreement Id
        :param job_id: str id of compute job that was returned from `start_compute_job`
        :param service_endpoint: str url of the provider service endpoint for compute service
        :param account_address: hex str the ethereum address of the consumer's account
        :param signature: hex str signed message to allow the provider to authorize the consumer

        :return: dict of job_id to result urls. When job_id is not provided, this will return
            result for each job_id that exist for the agreement_id
        """
        return DataServiceProvider._send_compute_request(
            'get', agreement_id, job_id, service_endpoint, account_address, signature
        )

    @staticmethod
    def get_url(config):
        """
        Return the DataProvider component url.

        :param config: Config
        :return: Url, str
        """
        _url = 'http://localhost:8030'
        if config.has_option('resources', 'provider.url'):
            _url = config.get('resources', 'provider.url') or _url

        _path = '/api/v1'
        return f'{_url}{_path}'

    @staticmethod
    def get_initialize_endpoint(service_endpoint):
        base_url = '/'.join(service_endpoint.split('/')[:-1])
        return f'{base_url}/initialize'

    @staticmethod
    def get_download_endpoint(config):
        """
        Return the url to consume the asset.

        :param config: Config
        :return: Url, str
        """
        return f'{DataServiceProvider.get_url(config)}/services/download'

    @staticmethod
    def get_compute_endpoint(config):
        """
        Return the url to execute the asset.

        :param config: Config
        :return: Url, str
        """
        return f'{DataServiceProvider.get_url(config)}/services/compute'

    @staticmethod
    def get_encrypt_endpoint(config):
        """
        Return the url to encrypt the asset.

        :param config: Config
        :return: Url, str
        """
        return f'{DataServiceProvider.get_url(config)}/services/encrypt'

    @staticmethod
    def write_file(response, destination_folder, file_name):
        """
        Write the response content in a file in the destination folder.
        :param response: Response
        :param destination_folder: Destination folder, string
        :param file_name: File name, string
        :return: bool
        """
        if response.status_code == 200:
            with open(os.path.join(destination_folder, file_name), 'wb') as f:
                for chunk in response.iter_content(chunk_size=None):
                    f.write(chunk)
            logger.info(f'Saved downloaded file in {f.name}')
        else:
            logger.warning(f'consume failed: {response.reason}')

    @staticmethod
    def _send_compute_request(http_method, agreement_id, job_id, service_endpoint, account_address, signature):
        compute_url = (
            f'{service_endpoint}'
            f'?signature={signature}'
            f'&serviceAgreementId={agreement_id}'
            f'&consumerAddress={account_address}'
            f'&jobId={job_id or ""}'
        )
        logger.info(f'invoke compute endpoint with this url: {compute_url}')
        method = getattr(DataServiceProvider._http_client, http_method)
        response = method(compute_url)
        print(f'got brizo execute response: {response.content} with status-code {response.status_code} ')
        if response.status_code != 200:
            raise Exception(response.content.decode('utf-8'))

        resp_content = json.loads(response.content.decode('utf-8'))
        if isinstance(resp_content, list):
            return resp_content[0]
        return resp_content

    @staticmethod
    def _get_file_name(response):
        try:
            return re.match(r'attachment;filename=(.+)',
                            response.headers.get('content-disposition'))[1]
        except Exception as e:
            logger.warning(f'It was not possible to get the file name. {e}')

    @staticmethod
    def _prepare_compute_payload(
            agreement_id, account_address, service_id, service_type, token_address, tx_id,
            signature=None, algorithm_did=None, algorithm_meta=None,
            output=None, job_id=None):
        assert algorithm_did or algorithm_meta, 'either an algorithm did or an algorithm meta must be provided.'

        if algorithm_meta:
            assert isinstance(algorithm_meta, AlgorithmMetadata), f'expecting a AlgorithmMetadata type ' \
                                                                  f'for `algorithm_meta`, got {type(algorithm_meta)}'
            algorithm_meta = algorithm_meta.as_dictionary()

        return {
            'signature': signature,
            'serviceAgreementId': agreement_id,
            'consumerAddress': account_address,
            'algorithmDID': algorithm_did,
            'algorithmMeta': algorithm_meta,
            'output': output or dict(),
            'jobId': job_id or "",
            'serviceId': service_id,
            'serviceType': service_type,
            'tokenAddress': token_address,
            'transferTxId': tx_id,

        }