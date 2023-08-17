# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import contextlib
import os

from jinja2 import Environment, FileSystemLoader


@contextlib.contextmanager
def pushd(new_dir):
    pre_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(pre_dir)


class PluginTemplate(object):
    def __init__(self, template_params):
        with pushd(os.path.normpath(os.path.dirname(__file__))):
            template_loader = FileSystemLoader(searchpath="./")
        self._template_env = Environment(loader=template_loader)

        self._plugin_name = template_params.plugin_name
        self._plugin_output_number = template_params.num_outputs
        self._plugin_output_dtype = template_params.output_dtype
        self._plugin_workspace_size = template_params.total_workspace_size
        self._plugin_source_code = template_params.cuda_source_code
        self._plugin_output_shape = self._parse_plugin_output_shape(
            template_params.output_shape
        )
        self._plugin_tensor_format = self._parse_plugin_tensor_format(
            template_params.tensor_type
        )
        self._plugin_device_function_configuration = (
            self._parse_plugin_device_function_configuration(
                template_params.device_function_configuration,
                template_params.device_function_list,
            )
        )
        self._plugin_workspace_constant = self._parse_plugin_workspace_constant(
            template_params.workspace_constant
        )

    class TensorDims:
        def __init__(self, nbdims, shape):
            self.nbdims = nbdims
            self.shape = tuple(shape)

        def __str__(self):
            return f"TensorDims(nbdims={self.nbdims}, shape={self.shape})"

        def __repr__(self):
            return str(self)

    class TensorFormat:
        def __init__(self, format, type):
            self.format = format
            self.type = type

        def __str__(self):
            return f"TensorFormat(format={self.format}, type={self.type})"

        def __repr__(self):
            return str(self)

    class Kernel:
        def __init__(
            self,
            name,
            grid_dim,
            block_dim,
            enqueue_params,
            kernel_params=None,
            code=None,
        ):
            self.name = name
            self.grid_dim = grid_dim
            self.block_dim = block_dim
            self.enqueue_params = enqueue_params
            self.kernel_params = kernel_params
            self.code = code

        def __str__(self):
            return f"Kernel(name={self.name}, grid_dim={self.grid_dim}, block_dim={self.block_dim}, enqueue_params={self.enqueue_params})"

        def __repr__(self):
            return str(self)

    class Constant:
        def __init__(self, pos, value, type, index, length):
            self.pos = pos
            self.value = value
            self.type = type
            self.index = index
            self.length = length

        def __str__(self):
            return f"Constant(pos={self.pos}, length={self.length}, type={self.type}, index={self.index})"

        def __repr__(self):
            return str(self)

    class Case:
        def __init__(
            self,
            batch_size,
            plugin_template,
            dy_plugin_input_size_type_without_bs=None,
            dy_plugin_output_size_type_without_bs=None,
        ):
            self.batch_size = batch_size
            self.plugin_template = plugin_template
            self.dy_plugin_input_size_type_without_bs = (
                dy_plugin_input_size_type_without_bs
            )
            self.dy_plugin_output_size_type_without_bs = (
                dy_plugin_output_size_type_without_bs
            )

    class Shape:
        def __init__(self, size, dtype):
            self.size = size
            self.dtype = dtype

    def _parse_plugin_output_shape(self, output_shape):
        plugin_output_shape = []
        for s in output_shape:
            nbdims = len(s)
            shape = s
            plugin_output_shape.append(self.TensorDims(nbdims, shape))
        return plugin_output_shape

    def _parse_plugin_tensor_format(self, tensor_type):
        plugin_tensor_format = []
        for dtype in tensor_type:
            plugin_tensor_format.append(self.TensorFormat("LINEAR", dtype))
        return plugin_tensor_format

    def _parse_plugin_device_function_configuration(
        self, device_function_configuration, device_function_list
    ):
        frequency = {}
        kernel_configuration = []
        for func_name in device_function_list:
            if func_name not in frequency.keys():
                frequency[func_name] = 0
                key_name = func_name
            else:
                frequency[func_name] += 1
                key_name = f"{func_name}_{frequency[func_name]}"

            kernel_configuration.append(
                self.Kernel(
                    func_name,
                    device_function_configuration[key_name]["grid_dim"],
                    device_function_configuration[key_name]["block_dim"],
                    device_function_configuration[key_name]["enqueue_params"],
                )
            )
        return kernel_configuration

    def _parse_plugin_workspace_constant(self, workspace_constant):
        plugin_constant_init = []
        for init_constant in workspace_constant.items():
            value_str = ", ".join(str(ele) for ele in init_constant[1][0])
            value_str = value_str.strip(",")
            plugin_constant_init.append(
                self.Constant(
                    init_constant[0],
                    value_str,
                    init_constant[1][1],
                    init_constant[1][2],
                    len(init_constant[1][0]),
                )
            )
        return plugin_constant_init

    def generate_header_file(self):
        raise Exception("not implement method")

    def generate_source_file(self):
        raise Exception("not implement method")

    def fill(self):
        plugin_header_path = f"./plugin/src/{self._plugin_name}.h"
        plugin_source_path = f"./plugin/src/{self._plugin_name}.cu"
        if os.path.isfile(plugin_header_path):
            os.remove(plugin_header_path)
        if os.path.isfile(plugin_source_path):
            os.remove(plugin_source_path)

        with pushd(os.path.normpath(os.path.dirname(__file__))):
            self.generate_header_file()
            self.generate_source_file()
            result = self._build_plugin()

        if result:
            return f"{os.path.dirname(os.path.abspath(__file__))}/plugin/lib/{self._plugin_name}.so"
        else:
            return False

    def _build_plugin(self):
        os.chdir("./plugin")

        os.system(f"make clean plugin_name={self._plugin_name}")
        os.system(f"make plugin_name={self._plugin_name}")

        os.chdir("../")
        return True


class StaticBatchPluginTemplate(PluginTemplate):
    """
    Fill in the useable params which generated by PluginTemplateParams to plugin template.
    The plugin template is compatible with TensorRT-8.0.
    """

    def __init__(
        self,
        template_params,
        TEMPLATE_HEADER_FILE="./plugin/trt8.0_plugin_h.template",
        TEMPLATE_SOURCE_FILE="./plugin/trt8.0_plugin_cu.template",
    ):
        super(StaticBatchPluginTemplate, self).__init__(template_params)

        self._template_header_file = TEMPLATE_HEADER_FILE
        self._template_source_file = TEMPLATE_SOURCE_FILE

    def generate_header_file(self):
        template = self._template_env.get_template(self._template_header_file)
        output_text = template.render(
            plugin_name=self._plugin_name,
            plugin_output_number=self._plugin_output_number,
            plugin_output_shape=self._plugin_output_shape,
            plugin_output_dtype=self._plugin_output_dtype,
            plugin_workspace_size=self._plugin_workspace_size,
            plugin_tensor_format=self._plugin_tensor_format,
        )
        with open("./plugin/src/{}.h".format(self._plugin_name), "w") as f:
            f.write(output_text)

    def generate_source_file(self):
        template = self._template_env.get_template(self._template_source_file)
        output_text = template.render(
            plugin_name=self._plugin_name,
            plugin_device_function_configuration=self._plugin_device_function_configuration,
            plugin_source_code=self._plugin_source_code,
            plugin_workspace_constant=self._plugin_workspace_constant,
        )
        with open("./plugin/src/{}.cu".format(self._plugin_name), "w") as f:
            f.write(output_text)
