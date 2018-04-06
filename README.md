base16-builder-ansible [![Build Status](https://travis-ci.org/mnussbaum/base16-builder-ansible.svg?branch=master)](https://travis-ci.org/mnussbaum/base16-builder-ansible)
================

This role builds and returns [Base16](https://github.com/chriskempson/base16)
themes. Base16 is a framework for generating themes for a wide variety of
applications like Vim, Bash or i3 with color schemes like Tomorrow Night or
Gruvbox.

This builder's goal is to make it easy to install and update Base16 colors
across a wide range of applications. Using Ansible as a Base16 builder gives us
a lot of flexibility. We can generate themes and either write them as
standalone files or embed the theme into larger config file templates. This is
particularly useful for applications that can only handle a single config file,
like i3.

Instead of downloading pre-rendered color scheme templates, this role builds
them on the fly. This lets us use Base16 color schemes that older template
repos might not have picked up yet, as well as ensuring that we're always using
the latest version of existing color schemes.

In addition to the examples below, check out the [demo](demo) directory for a
full Ansible playbook that lets you switch between color schemes for Vim, i3
and Bash.

## Example usages

```yaml
---
roles:
  - mnussbaum.base16-builder-ansible

tasks:
  # Build a single color scheme and template and assign it to a variable
  - base16_builder:
      scheme: tomorrow-night
      template: shell
    register: base16_schemes

  # It helps to print out the registered result once with debug to figure out how
  # to access any particular scheme and template. Each Base16 template repo (e.g.
  # "shell", "i3") can include multiple template files to render out, so every
  # template repo will register their output at a slightly different index path in
  # the result object.

  - debug:
      var: base16_schemes

  # I'll elide the rendered contents for readability, but result will look like this:
  #
  # "base16_schemes": {
  #   "changed": true,
  #   "failed": false,
  #   "schemes": {
  #     "tomorrow-night": {
  #       "shell": {
  #         "scripts": {
  #           "base16-tomorrow-night.sh": "#!/bin/sh\n# base16-shell ..."
  #         }
  #       }
  #     }
  #   }
  # }

  # You can write the generated color schemes to a file or render them into your
  # own templates
  - copy:
      content: "{{ base16_schemes['schemes']['tomorrow-night']['shell']['scripts']['base16-tomorrow-night.sh'] }}"
      dest: /my/bash/profile/dir/tomorrow-night-shell.sh

  # Build every template for a single color scheme
  - base16_builder:
      scheme: tomorrow-night
    register: base16_schemes

  # Build every color scheme for a single template
  - base16_builder:
      template: shell
    register: base16_schemes

  # Build every color scheme for every template
  - base16_builder: {}
    register: base16_schemes

  # Download latest color scheme and template source files, but don't build anything
  - base16_builder:
      update: yes
      build: no

  # Download updates for and rebuild a single template and scheme
  - base16_builder:
      update: yes
      scheme: tomorrow-night
      template: shell
    register: base16_schemes

  # If you make your own Base16 color scheme and want to reference it before it's
  # pulled into the master list of schemes you can fork the master list, add a
  # reference to your scheme, and then use your list fork as the schemes source
  # arg here. The same applies to new template repos and the master template
  # list. Those master lists are available at:
  #
  #   https://github.com/chriskempson/base16-schemes-source
  #   https://github.com/chriskempson/base16-templates-source
  #
  - base16_builder:
      scheme: my-brand-new-color-scheme
      template: shell
      schemes_source: http://github.com/my-user/my-schemes-source-fork
      templates_source: http://github.com/my-user/my-templates-source-fork
```

## Options

```yaml
scheme:
  description:
    - Set this to the name of a color scheme to only build that one scheme, instead of building all, which is the default
    - Only building a single scheme is much faster then building all
  required: false
  type: string
  default: Build all schemes
template:
  description:
    - Set this to the name of a template to only build that one template instead of building all, which is the default
    - Only building a single template is much faster then building all
  required: false
  type: string
  default: Build all templates
cache_dir:
  description:
    - Parent directory to store cloned scheme, template and source data
    - Will be created if it doesn't exist already
    - The default looks for the $XDG_CACHE_DIR env var, then a ~/.cache dir, and falls back to the platform's temp dir if the first two don't exist
  required: false
  type: string
  default: First available of $XDG_CACHE_DIR, $HOME/.cache, or platform derived temp dir
schemes_source:
  description:
    - Git repo URL to clone for scheme source data
    - These repos include a list.yaml file that maps scheme names to Git source repos
  required: false
  type: string
  default: https://github.com/chriskempson/base16-schemes-source
templates_source:
  description:
    - Git repo URL to clone for template source data
    - These repos include a list.yaml file that maps template names to Git source repos
  required: false
  type: string
  default: https://github.com/chriskempson/base16-templates-source
update:
  description:
    - Clone or pull color scheme and template sources
    - By default will update all schemes and templates, but will repect scheme and template args
    - Build will donwload any missing data, so you never _need_ to call update
  required: false
  type: bool
  default: no
build:
  description:
    - Set to "no" to disable building of any color schemes or templates
    - Useful to set to "no" when used with update to only download sources
  required: false
  type: bool
  default: yes
```

## Dependencies

* Python 2.7, or 3.4 or greater
* Ansible
* [Pystache](https://github.com/defunkt/pystache), which you can install with:

  ```bash
  pip install pystache
  ```

## Installation

You can install this role with
[`ansible-galaxy`](https://galaxy.ansible.com/intro). Check out the
`ansible-galaxy` docs for all the different ways you can install roles, but the
simplest is just:

    $ ansible-galaxy install mnussbaum.base16-builder-ansible

After you've installed the role you need to reference it, and then you can use
the `base16_builder` module it provides. Here's a very short example of this:

```yaml
---
roles:
  - mnussbaum.base16-builder-ansible

tasks:
  - base16_builder:
      scheme: tomorrow-night
      template: shell
    register: base16_schemes
```

If you don't want to, or can't, use `ansible-galaxy`, then you can clone this
repo and drop it directly into your [Ansible roles
path](https://docs.ansible.com/ansible/latest/playbooks_reuse_roles.html#role-search-path).

Either way you install the role, don't forget to also install the Pystache
dependency as mentioned above.

## Developing

This project uses [Pipenv](https://github.com/pypa/pipenv) to install
dependencies. To run the tests:

```bash
pip install --user pipenv
pipenv install --dev
pipenv run nose2
```

## License

[MIT](LICENSE)

## To do

* Parallelize git pulls
* Make the tests use fixtures instead of actually cloning repos
* Allow schemes and templates to be local file paths to ease developing new ones
* Allow the Base16 unclaimed schemes to be used too
