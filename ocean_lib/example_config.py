#
# Copyright 2022 Ocean Protocol Foundation
# SPDX-License-Identifier: Apache-2.0
#

import copy
import logging

from enforce_typing import enforce_types

logging.basicConfig(level=logging.INFO)

DEFAULT_METADATA_CACHE_URI = "http://172.15.0.5:5000"
METADATA_CACHE_URI = "https://v4.aquarius.oceanprotocol.com"
DEFAULT_PROVIDER_URL = "http://172.15.0.4:8030"

config_defaults = {
    "NETWORK_NAME": "development",
    "TRANSACTION_TIMEOUT": 10 * 60,  # 10 minutes
    "METADATA_CACHE_URI": "http://172.15.0.5:5000",
    "PROVIDER_URL": "http://172.15.0.4:8030",
    "DOWNLOADS_PATH": "consume-downloads",
}

CONFIG_NETWORK_HELPER = {
    "mainnet": {
        "PROVIDER_URL": "https://v4.provider.mainnet.oceanprotocol.com",
    },
    "goerli": {
        "PROVIDER_URL": "https://v4.provider.goerli.oceanprotocol.com",
    },
    "bsc": {
        "PROVIDER_URL": "https://v4.provider.bsc.oceanprotocol.com",
    },
    "polygon": {
        "PROVIDER_URL": "https://v4.provider.polygon.oceanprotocol.com",
    },
    "energyweb": {
        "PROVIDER_URL": "https://v4.provider.energyweb.oceanprotocol.com",
        "TRANSACTION_TIMEOUT": 60,
    },
    "moonriver": {
        "PROVIDER_URL": "https://v4.provider.moonriver.oceanprotocol.com",
        "TRANSACTION_TIMEOUT": 60,
    },
    "moonbase": {
        "PROVIDER_URL": "https://v4.provider.moonbase.oceanprotocol.com",
        "TRANSACTION_TIMEOUT": 60,
    },
    "development": {
        "PROVIDER_URL": DEFAULT_PROVIDER_URL,
        "TRANSACTION_TIMEOUT": 2,
    },
    "celoalfajores": {
        "PROVIDER_URL": "https://provider.celoalfajores.oceanprotocol.com",
        "TRANSACTION_TIMEOUT": 60,
    },
    "mumbai": {
        "PROVIDER_URL": "https://v4.provider.mumbai.oceanprotocol.com",
        "TRANSACTION_TIMEOUT": 60,
    },
}


@enforce_types
def get_config_dict(network_name: str) -> dict:
    if network_name not in CONFIG_NETWORK_HELPER:
        raise ValueError("The chain id for the specific RPC could not be fetched!")

    config_helper = copy.deepcopy(config_defaults)
    config_helper.update(CONFIG_NETWORK_HELPER[network_name])
    config_helper["NETWORK_NAME"] = network_name

    if network_name != "development":
        config_helper["METADATA_CACHE_URI"] = METADATA_CACHE_URI
    else:
        config_helper[
            "ADDRESS_FILE"
        ] = "~/.ocean/ocean-contracts/artifacts/address.json"

    return config_helper


class ExampleConfig:
    @staticmethod
    @enforce_types
    def get_config(network_name=None) -> dict:
        """Return config dict containing default values for a given network.
        Chain ID is determined by querying the RPC specified by network_url.
        """

        if not network_name:
            network_name = "development"

        config_dict = get_config_dict(network_name)

        return config_dict
