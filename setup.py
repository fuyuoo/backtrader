#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2023 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
import os.path
import codecs  # To use a consistent encoding
import setuptools

here = os.path.abspath(os.path.dirname(__file__))

# Get the long description from the relevant file
with codecs.open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

# Package name
pname = 'backtrader'

# Get the version ... execfile is only on Py2 ... use exec + compile + open
vname = 'version.py'
with open(os.path.join(pname, vname)) as f:
    exec(compile(f.read(), vname, 'exec'))

# Generate links
gurl = 'https://github.com/mementum/' + pname
gdurl = gurl + '/tarball/' + __version__

setuptools.setup(
    name=pname,

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=__version__,

    description='BackTesting Engine',
    long_description=long_description,

    # The project's main homepage.
    url=gurl,
    download_url=gdurl,

    # Author details
    author='Daniel Rodriguez',
    author_email='danjrod@gmail.com',

    # Choose your license
    license='GPLv3+',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 5 - Production/Stable',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',

        # Indicate which Topics are covered by the package
        'Topic :: Software Development',
        'Topic :: Office/Business :: Financial',

        # Pick your license as you wish (should match "license" above)
        ('License :: OSI Approved :: ' +
         'GNU General Public License v3 or later (GPLv3+)'),

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',

        # Operating Systems on which it runs
        'Operating System :: OS Independent',
    ],

    # What does your project relate to?
    keywords=['trading', 'development'],

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=setuptools.find_packages(exclude=['docs', 'docs2', 'samples']),
    # packages=['backtrader', '],

    # List run-time dependencies here.
    # These will be installed by pip when your
    # project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        'pandas>=2,<4',
        'pyarrow>=15',
        'pydantic>=2,<3',
        'PyYAML>=6,<7',
        'tushare>=1.4',
    ],

    # List additional groups of dependencies here
    # (e.g. development dependencies).
    # You can install these using the following syntax, for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'plotting':  ['matplotlib'],
        'tuning':  ['optuna>=3,<5'],
    },

    # If there are data files included in your packages that need to be
    # installed, specify them here.  If using Python 2.6 or less, then these
    # have to be included in MANIFEST.in as well.
    # package_data={'sample': ['package_data.dat'],},

    # Although 'package_data' is the preferred approach, in some case you may
    # need to place data files outside of your packages. See:
    # http://docs.python.org/3.4/distutils/setupscript.html#installing-additional-files
    # In this case, 'data_file' will be installed into '<sys.prefix>/my_data'
    # data_files=[('my_data', ['data/data_file'])],

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    # entry_points={'console_scripts': ['sample=sample:main',],},
    entry_points={'console_scripts': [
        'btrun=backtrader.btrun:btrun',
        'att-run-plan=attbacktrader.cli.run_plan:main',
        'att-compare-runs=attbacktrader.cli.compare_runs:main',
        'att-compare-environment-fit=attbacktrader.cli.compare_environment_fit:main',
        'att-generate-attribution-filter-experiments=attbacktrader.cli.attribution_filter_experiments:main',
        'att-generate-market-segment-runs=attbacktrader.cli.market_segment_runs:main',
        'att-market-type-summary=attbacktrader.cli.market_type_summary:main',
        'att-strategy-adaptation-matrix=attbacktrader.cli.strategy_adaptation_matrix:main',
        'att-strategy-adaptation-drilldown=attbacktrader.cli.strategy_adaptation_drilldown:main',
        'att-strategy-variant-drafts=attbacktrader.cli.strategy_variant_drafts:main',
        'att-generate-strategy-variant-runs=attbacktrader.cli.strategy_variant_runs:main',
        'att-strategy-variant-validation=attbacktrader.cli.strategy_variant_validation:main',
        'att-strategy-variant-attribution=attbacktrader.cli.strategy_variant_attribution:main',
        'att-attribution-matrix=attbacktrader.cli.attribution_matrix:main',
        'att-attribution-summary=attbacktrader.cli.attribution_summary:main',
        'att-attribution-wide-samples=attbacktrader.cli.attribution_wide_samples:main',
        'att-prepare-attribution-reference=attbacktrader.cli.prepare_attribution_reference:main',
        'att-environment-fit=attbacktrader.cli.environment_fit:main',
        'att-single-factor-attribution=attbacktrader.cli.single_factor_attribution:main',
        'att-bayesian-factor-discovery=attbacktrader.cli.bayesian_factor_discovery:main',
        'att-generate-entry-factor-validation-manifest=attbacktrader.cli.entry_factor_validation_manifest:main',
        'att-generate-entry-factor-pairwise-combination-manifest=attbacktrader.cli.entry_factor_pairwise_combination_manifest:main',
        'att-run-entry-factor-validation=attbacktrader.cli.entry_factor_validation_run:main',
        'att-run-entry-factor-validation-matrix=attbacktrader.cli.entry_factor_validation_matrix:main',
        'att-classify-entry-factor-validation=attbacktrader.cli.entry_factor_validation_classification:main',
        'att-scored-entry-allocation-tuning=attbacktrader.cli.scored_entry_allocation_tuning:main',
        'att-strategy-environment-profile=attbacktrader.cli.strategy_environment_profile:main',
        'att-review-brief=attbacktrader.cli.review_brief:main',
        'att-review-expand-samples=attbacktrader.cli.review_expand_samples:main',
        'att-review-experiment-candidates=attbacktrader.cli.review_experiment_candidates:main',
        'att-review-experiment-confirm=attbacktrader.cli.review_experiment_confirm:main',
        'att-review-experiment-drafts=attbacktrader.cli.review_experiment_drafts:main',
        'att-review-findings=attbacktrader.cli.review_findings:main',
        'att-review-golden-check=attbacktrader.cli.review_golden_check:main',
        'att-review-packet=attbacktrader.cli.review_packet:main',
        'att-review-result=attbacktrader.cli.review_result:main',
        'att-review-sample=attbacktrader.cli.review_sample:main',
        'att-run-data-attribution-index=attbacktrader.cli.run_data_attribution_index:main',
        'att-run-catalog=attbacktrader.cli.run_catalog:main',
        'att-experiment-lifecycle=attbacktrader.cli.experiment_lifecycle:main',
        'att-experiment-decisions=attbacktrader.cli.experiment_decisions:main',
        'att-workbench-closure-snapshot=attbacktrader.cli.workbench_closure_snapshot:main',
        'att-workbench-closure-golden-check=attbacktrader.cli.workbench_closure_golden_check:main',
        'att-ai-skill-entry-contract=attbacktrader.cli.ai_skill_entry_contract:main',
        'att-validate-strategy-integration=attbacktrader.cli.strategy_integration_validation:main',
        'att-run-data-dictionary=attbacktrader.cli.run_data_dictionary:main',
        'att-run-data-drilldown=attbacktrader.cli.run_data_drilldown:main',
        'att-run-data-drilldown-batch=attbacktrader.cli.run_data_drilldown_batch:main',
        'att-run-data-overview=attbacktrader.cli.run_data_overview:main',
        'att-validate-run-regression=attbacktrader.cli.validate_run_regression:main',
        'att-tushare-backtest=attbacktrader.cli.tushare_backtest:main',
    ]},

    scripts=['tools/bt-run.py'],
)
