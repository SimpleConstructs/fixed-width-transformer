import dataclasses
import os
import re
import sys
import yaml
from transformer.library import exceptions
from transformer.library import common, logger, aws_service
from transformer.validator import ValidatorConfig
from transformer import source_mapper

log = logger.set_logger(__name__)

current_module = sys.modules[__name__]


class ExecutorConfig:
    _config = dict
    _exact_config = dict

    def __init__(self, key: str, local=None, inline=None):
        try:
            self._config = self._retrieve_config(local, inline)
            self._set_exact_config(key)
        except Exception as e:
            print(e)
            raise e

    def _retrieve_config(self, local=None, inline=None) -> dict:
        if inline:
            cfg = yaml.safe_load(inline)
            if isinstance(cfg, dict):
                return cfg
            raise exceptions.InvalidConfigError()
        if local is None:
            # To retrieve config using environment variables
            if os.environ['config_type'] == "local":
                env_config = common.check_environment_variables(["config_name"])
                log.info(f"Using Local Configuration file [{env_config[0]}]")
                with open(env_config[0], 'r') as file:
                    cfg = yaml.safe_load(file)
                    if isinstance(cfg, dict):
                        return cfg
                    raise exceptions.InvalidConfigError()

            # Retrieve S3 remote config
            required_configs = ["config_bucket", "config_name"]
            env_config = common.check_environment_variables(required_configs)
            log.info(f"Using External Configuration file from S3 bucket [{env_config[0]}] with key [{env_config[1]}")
            cfg = yaml.safe_load(
                aws_service.download_s3_as_bytes(env_config[0], env_config[1]).read()
            )
            if isinstance(cfg, dict):
                return cfg
            raise exceptions.InvalidConfigError()
        else:
            log.info(f"Using Local Configuration file [{local}]")
            try:
                with open(local, 'r') as file:
                    cfg = yaml.safe_load(file)
                    if isinstance(cfg, dict):
                        return cfg
                    raise
            except FileNotFoundError as e:
                raise exceptions.MissingConfigError(e)

    def _set_exact_config(self, key):
        if self._config['files'] is None:
            raise exceptions.InvalidConfigError()
        for k in self._config['files']:
            pattern = self._config['files'][k]['pattern']
            if re.match(pattern, key):
                self._exact_config = self._config['files'][k]
                return
        raise exceptions.MissingConfigError(
            f"No matching regex pattern found for file with name [{key}]. Please check configuration yaml file")

    def get_config(self):
        return self._config

    def get_exact_config(self):
        return self._exact_config


@dataclasses.dataclass
class SourceMapperConfig:
    _mappers = [source_mapper.MapperConfig]

    def __init__(self, config: ExecutorConfig):
        self.set_mappers(config.get_exact_config())

    def set_mappers(self, config: dict, file_format="source"):
        mappers = []
        if file_format in config.keys():
            if config[file_format] is None:
                raise exceptions.InvalidConfigError(f"{file_format} segment cannot be empty")
        else:
            raise exceptions.InvalidConfigError(f"{file_format} segment is missing in configuration")

        has_header = True if 'header' in config[file_format].keys() else False
        has_footer = True if 'footer' in config[file_format].keys() else False
        for segment in config[file_format]:
            names = []
            specs = []
            validators = []
            for field in config[file_format][segment]['format']:
                names.append(field['name'])
                specs.append(self._converter(field['spec']))
                if 'validators' in field.keys():
                    for validator in field['validators']:
                        validators.append(ValidatorConfig(validator['name'], segment, field['name'], validator['arguments']))
            mappers.append(source_mapper.MapperConfig(
                name=config[file_format][segment]['mapper'],
                segment=segment,
                names=names,
                specs=specs,
                skipHeader=has_header,
                skipFooter=has_footer,
                validations=validators
                )
            )
        self._mappers = mappers

    def _converter(self, data: str):
        if not isinstance(data, str):
            raise ValueError("Invalid Type for input [data]")
        if ',' not in data:
            raise ValueError('[data] must be comma seperated! eg. 1,2')
        splits = data.split(',')
        return tuple([int(splits[0].strip()), int(splits[1].strip())])

    def get_mappers(self):
        return self._mappers


@dataclasses.dataclass
class ResultMapperConfig:
    _result_config: dict
    _validations: []

    def __init__(self, config: ExecutorConfig):
        self.set_result_config(config.get_exact_config())
        self.set_validators(config.get_exact_config())

    def set_result_config(self, config):
        # TODO: Enhance if need to formalize the config in a better flow.
        try:
            if 'format' in config['output']:
                self._result_config = config['output']['format']
            else:
                self._result_config = {}
        except KeyError as e:
            raise exceptions.InvalidConfigError(e)

    def set_validators(self, config):
        pass

    def get_result_config(self):
        return self._result_config

    def get_validators(self):
        return self._validations


@dataclasses.dataclass
class ResultConfig:
    _name: str
    _arguments: dict

    def __init__(self, config: ExecutorConfig):
        if 'result' not in config.get_exact_config()['output'].keys():
            raise exceptions.InvalidConfigError('result segment is missing. Please ensure configuration is provided')
        if config.get_exact_config()['output']['result'] is None or not config.get_exact_config()['output']['result']:
            raise exceptions.InvalidConfigError('result segment cannot be empty. Please ensure configuration is valid')

        self._name = config.get_exact_config()['output']['result']['name']
        self._arguments = {}
        if 'arguments' in config.get_exact_config()['output']['result'].keys():
            self._arguments = config.get_exact_config()['output']['result']['arguments']

    def get_name(self) -> str:
        return self._name

    def get_arguments(self) -> dict:
        return self._arguments
