#!/usr/bin/python

# -*- coding: utf-8 -*-

ANSIBLE_METADATA = {
    'metadata_version': '1.1',
    'status': ['preview'],
    'supported_by': 'community'
}

DOCUMENTATION = '''
---
module: base16_builder

short_description: Builds base16 color schemes

description: Builds base16 color schemes

options:
    update:
        description:
            - Refresh color scheme and template sources
        required: false
        type: bool
        default: no
    build:
        description:
            - Set to no to not build any color schemes or templates
        required: false
        type: bool
        default: yes
    scheme:
        description:
            - Name of a single color scheme to build
        required: false
        type: string
        default: Build all schemes
    template:
        description:
            - Name of a single template to build
        required: false
        type: string
        default: Build all templates
    cache_dir:
        description:
            - Directory to store cloned scheme and template source data
        required: false
        type: string
        default: First available of $XDG_CACHE_DIR, $HOME/.cache, or platform derived temp dir
    schemes_source:
        description:
            - Git repo URL to clone for scheme source data
        required: false
        type: string
        default: https://github.com/chriskempson/base16-schemes-source
    templates_source:
        description:
            - Git repo URL to clone for template source data
        required: false
        type: string
        default: https://github.com/chriskempson/base16-templates-source

author:
    - Michael Nussbaum (@mnussbaum)
'''

EXAMPLES = '''
# Build a single color scheme and template and assign it to a variable
- name: Build solarflare for i3
  base16_builder:
    scheme: solarflare
    template: i3
  register: base16_schemes

# You can write the generated color schemes to a file or render them into config templates
- copy:
    content: "{{ base16_schemes['solarflare']['i3'] }}"
    dest: /tmp/solarflare-i3.config

# Build every template for the a single color scheme
- name: Build solarflare for every template
  base16_builder:
    scheme: solarflare
  register: base16_schemes

# Build every color scheme for a single template
- name: Build every color scheme for i3
  base16_builder:
    template: i3
  register: base16_schemes

# Build every color scheme for every template
- name: Build every color scheme for every template
  base16_builder: {}
  register: base16_schemes

# Ensure the latest color schemes and templates are downloaded, don't build anything
- name: Update base16 schemes and templates
  base16_builder:
    update: yes
    build: no

# Ensure the latest color schemes and templates are downloaded, build one
- name: Update base16 schemes and templates and build solarflare for i3
  base16_builder:
    update: yes
    scheme: solarflare
    template: i3
  register: base16_schemes

# Ensure the latest color schemes and templates are downloaded, from custom repos
- name: Update base16 schemes and templates from custom repos
  base16_builder:
    update: yes
    build: no
    data_dir: http://github.com/my_user/my_schemes_sources_fork
    templates_data_dir: http://github.com/my_user/my_templates_sources_fork
'''

RETURN = '''
schemes:
    description: A dict of color schemes mapped to nested dicts of rendered templates
    type: dict
'''

import os 
import shutil
import tempfile
import yaml

from ansible.module_utils.basic import AnsibleModule

PYSTACHE_ERR = None
try:
    import pystache
except (ImportError, ModuleNotFoundError) as err:
    PYSTACHE_ERR = err


def open_yaml(path):
    with open(path) as yaml_file:
        return yaml.load(yaml_file)


class GitRepo(object):
    def __init__(self, builder, repo, path):
        self.builder = builder
        self.module = builder.module
        self.git_path = self.module.get_bin_path('git', True)
        self.repo = repo
        self.path = path
        self.git_config_path = os.path.join(self.path, '.git', 'config')

    def clone_or_pull(self):
        if not self.clone_if_missing():
            self.builder.result['changed'] = True
            if self.module.check_mode:
                return

            self.module.run_command(
                [self.git_path, 'pull'],
                cwd=self.path,
                check_rc=True,
            )


    def clone_if_missing(self):
        if not os.path.exists(os.path.dirname(self.path)):
            self.builder.result['changed'] = True
            if self.module.check_mode:
                return

            os.makedirs(os.path.dirname(self.path))

        if self._repo_at_path():
            return False

        self.builder.result['changed'] = True
        if self.module.check_mode:
            return

        # If a different repo is at the given path, replace it
        if os.path.exists(self.git_config_path):
            shutil.rmtree(self.path)

        self.module.run_command(
            [self.git_path, 'clone', self.repo, self.path],
            check_rc=True,
        )

        return True

    def _repo_at_path(self):
        """
        This is a very rough heuristic to tell if there's a  git repo at the
        path that points to the same repo URL we were given. It would be better
        to parse the file, but that would pull in another dependency :/
        """
        if not os.path.exists(self.git_config_path):
            return False

        with open(self.git_config_path) as git_config:
            if 'url = {}'.format(self.repo) in git_config.read():
                return True

        return False


class Base16SourceRepo(object):
    def __init__(self, builder, source_repo_class):
        self.builder = builder
        self.module = builder.module
        self.source_repo_class = source_repo_class
        self.source_type = source_repo_class.source_type
        self.git_repo = GitRepo(
            builder,
            self.module.params['{}_source'.format(self.source_type)],
            os.path.join(
                self.module.params['cache_dir'],
                'base16-builder-ansible',
                'sources',
                self.source_type,
            ),
        )

    def _source_repos(self):
        for (source_family, source_url) in open_yaml(os.path.join(
            self.git_repo.path,
            'list.yaml',
        )).items():
            # Not sure if caching this value would be good or not
            yield self.source_repo_class(
                self.builder,
                source_family,
                source_url,
                os.path.join(
                    self.module.params['cache_dir'],
                    'base16-builder-ansible',
                    self.source_type,
                    source_family,
                ),
            )

    def sources(self):
        self.git_repo.clone_if_missing()
        for source_repo in self._source_repos():
            for source in source_repo.sources():
                yield source

    def update(self):
        self.git_repo.clone_or_pull()
        for source_repo in self._source_repos():
            source_repo.clone_or_pull() 


class Scheme(object):
    def __init__(self, builder, path):
        self.builder = builder
        self.module = builder.module
        self.path = path
        self.data = {}
        self._slug = None

        self.base16_vars = {
            'scheme-author': self._data()['author'],
            'scheme-name': self._data()['scheme'],
            'scheme-slug': self.slug(),
        }
        self.computed_bases = False

    def _data(self):
        if self.data:
            return self.data

        self.data = open_yaml(self.path)
        return self.data

    def slug(self):
        if self._slug:
            return self._slug

        self._slug = os.path.splitext(
            os.path.basename(self.path)
        )[0].lower().replace(' ', ' ')

        return self._slug

    def base16_variables(self):
        if self.computed_bases:
            return self.base16_vars

        for base in ['{:02X}'.format(i) for i in range(16)]:
            base_key = 'base{}'.format(base)
            base_hex_key = '{}-hex'.format(base_key)
            self.base16_vars.update({
                base_hex_key: self._data()[base_key],
                '{}-r'.format(base_hex_key): self._data()[base_key][0:2],
                '{}-g'.format(base_hex_key): self._data()[base_key][2:4],
                '{}-b'.format(base_hex_key): self._data()[base_key][4:6],
            })
            self.base16_vars.update({
                '{}-rgb-r'.format(base_hex_key): str(int(self.base16_vars[base_hex_key + '-r'],  16)),
                '{}-rgb-g'.format(base_hex_key): str(int(self.base16_vars[base_hex_key + '-g'], 16)),
                '{}-rgb-b'.format(base_hex_key): str(int(self.base16_vars[base_hex_key + '-b'], 16)),
                '{}-dec-r'.format(base_hex_key): str(int(self.base16_vars[base_hex_key + '-r'], 16) / 255),
                '{}-dec-g'.format(base_hex_key): str(int(self.base16_vars[base_hex_key + '-g'], 16) / 255),
                '{}-dec-b'.format(base_hex_key): str(int(self.base16_vars[base_hex_key + '-b'], 16) / 255),
            })

        self.computed_bases = True
        return self.base16_vars



class SchemeRepo(object):
    source_type = 'schemes'

    def __init__(self, builder, name, scheme_url, scheme_path):
        self.builder = builder
        self.module = builder.module
        self.name = name
        self.git_repo = GitRepo(
            self.builder,
            scheme_url,
            scheme_path,
        )

    def sources(self):
        # Only clone and yield scheme repos that could contain the requested
        # scheme.  We still need to do an exact comparison with the scheme slug
        # to only yield a single requested scheme though.
        module_scheme_arg = self.module.params.get('scheme')
        if module_scheme_arg and not self.name in module_scheme_arg:
            return

        self.git_repo.clone_if_missing()

        for path in os.listdir(self.git_repo.path):
            if os.path.splitext(path)[1] in ['.yaml', '.yml']:
                # Cache schemes here?
                scheme = Scheme(self.builder, os.path.join(self.git_repo.path, path))
                if module_scheme_arg and module_scheme_arg not in scheme.slug():
                    continue

                yield scheme

    def clone_or_pull(self):
        self.git_repo.clone_or_pull()


class Template(object):
    def __init__(self, builder, family, path, config):
        self.builder = builder
        self.module = builder.module
        self.family = family
        self.path = path
        self.config = config
        self.renderer = pystache.Renderer(search_dirs=os.path.dirname(self.path))

    def build(self, scheme):
        # os.path.join(
        #     os.path.dirname(self.path),
        #     self.config['output'],
        #     'base16-{}.{}'.format(scheme.slug(), self.config['extension']),
        # )
        return {
            'output_dir': self.config['output'],
            'output_file_name': 'base16-{}{}'.format(
                scheme.slug(),
                self.config['extension'],
            ),
            'output': self.renderer.render_path(
                self.path,
                scheme.base16_variables(),
            ),
        }



class TemplateRepo(object):
    source_type = 'templates'

    def __init__(self, builder, name, template_url, template_path):
        self.builder = builder
        self.module = builder.module
        self.name = name
        self.git_repo = GitRepo(
            self.builder,
            template_url,
            template_path,
        )
        self.templates_dir = os.path.join(self.git_repo.path, 'templates')

    def sources(self):
        module_template_arg = self.module.params.get('template')
        if module_template_arg and self.name != module_template_arg:
            return

        self.git_repo.clone_if_missing()

        for path in os.listdir(self.templates_dir):
            (file_name, file_ext) = os.path.splitext(path)
            if file_name != 'config' or file_ext not in ['.yaml', '.yml']:
                continue

            for template_name, template_config in open_yaml(os.path.join(
                self.templates_dir,
                path,
            )).items():
                # Cache here?
                yield Template(
                    self.builder,
                    self.name,
                    os.path.join(self.templates_dir, '{}.mustache'.format(template_name)),
                    template_config,
                )

    def clone_or_pull(self):
        self.git_repo.clone_or_pull()


class Base16Builder(object):
    def __init__(self, module):
        self.module = module

        self.schemes_repo = Base16SourceRepo(self, SchemeRepo)
        self.templates_repo = Base16SourceRepo(self, TemplateRepo)

        self.result = dict(
            changed=False,
            schemes=dict(),
        )

    def run(self):
        if PYSTACHE_ERR:
            self.module.fail_json(
                msg='Failed to import pystache. Type `pip install pystache` - {}'.format(PYSTACHE_ERR),
                **self.result
            )

        if self.module.params['update']:
            self.schemes_repo.update()
            self.templates_repo.update()
            self.result['changed'] = True

        if not self.module.params['build']:
            self.module.exit_json(**self.result)

        for scheme in self.schemes_repo.sources():
            # Not sure if this should be the slug or the family
            scheme_result = {}
            self.result['schemes'][scheme.slug()] = scheme_result
            for template in self.templates_repo.sources():
                build_result = template.build(scheme)
                if not scheme_result.get(template.family):
                    scheme_result[template.family] = {}

                template_family_result = scheme_result[template.family]

                if not template_family_result.get(build_result['output_dir']):
                    template_family_result[build_result['output_dir']] = {}

                template_result = template_family_result[build_result['output_dir']]
                template_result[build_result['output_file_name']] = build_result['output']

        self.module.exit_json(**self.result)


def main():
    if 'XDG_CACHE_DIR' in os.environ.keys():
        default_cache_dir = os.environ['XDG_CACHE_DIR']
    elif os.path.exists(os.path.join(os.path.expanduser('~'), '.cache')):
        default_cache_dir = os.path.join(os.path.expanduser('~'), '.cache')
    else:
        default_cache_dir = tempfile.gettempdir()

    module = AnsibleModule(
        argument_spec=dict(
            update=dict(type='bool', required=False, default=False),
            build=dict(type='bool', required=False, default=True),
            scheme=dict(type='str', required=False),
            template=dict(type='str', required=False),
            cache_dir=dict(type='str', required=False, default=default_cache_dir),
            schemes_source=dict(type='str', required=False, default='https://github.com/chriskempson/base16-schemes-source'),
            templates_source=dict(type='str', required=False, default='https://github.com/chriskempson/base16-templates-source'),
        ),
        supports_check_mode=True,
    )

    return Base16Builder(module).run()


if __name__ == '__main__':
    main()
