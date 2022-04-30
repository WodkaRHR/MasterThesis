# Get two levels above `__file__` to import thesis modules

from copy import deepcopy
from re import sub
import yaml
import os
import os.path as osp

# Configurations to be copied from the base
BASE_KEYS = ['seml', 'slurm', 'fixed', 'grid']

def build():
    dir = osp.dirname(__file__)
    fn, suffix = osp.splitext(osp.basename(__file__))
    with open(osp.join(dir, fn + '.base.yaml')) as f:
        base = yaml.safe_load(f)

    for dataset, jobs in (('cora_full', 8),  ('amazon_photo', 4), ('citeseer', 8), ('pubmed', 3), ('coauthor_cs', 3)):
        cfg = deepcopy({k : base[k] for k in BASE_KEYS})
        cfg['fixed']['data.dataset'] = dataset
        cfg['slurm']['experiments_per_job'] = jobs
        if  dataset == 'ogbn_arxiv' or dataset == 'pubmed' or dataset == 'coauthor_cs':
            cfg['slurm']['sbatch_options']['mem'] = '512G'
        if dataset == 'ogbn_arxiv':
            cfg['grid']['run.split_idx'] = {'type' : 'choice', 'options' : [0]}

        build_experiments(cfg)

        outfile = osp.join(dir, fn, f'{dataset}.yaml')
        os.makedirs(osp.dirname(outfile), exist_ok=True)
        with open(outfile, 'w+') as f:
            yaml.dump(deepcopy(cfg), f)
        print(f'Wrote configuration file to {outfile}')

def apply_no_edges(cfg):
    cfg = deepcopy(cfg)
    cfg.setdefault('model_kwargs', {})
    cfg.setdefault('name', '')
    cfg['model_kwargs'] |= {'remove_edges' : True}
    cfg['name'] += '-no-edges'
    return cfg

def build_experiments(cfg):
    for ood_type, ood_type_short in (('left-out-classes', 'loc'), ('perturbations', 'per')):

        # Build the evaluation pipeline
        pipeline_all_eval_modes = []

        for eval_mode in ('val', 'test'): # Run evaluation both on validation and test set
            # Build an evaluation pipeline for the ood type
            pipeline = []
            pipeline += [
                {
                    'type' : 'EvaluateAccuracy',
                    'evaluate_on' : [eval_mode],
                },
                apply_no_edges({
                    'type' : 'EvaluateAccuracy',
                    'evaluate_on' : [eval_mode],
                }),
                {
                    'type' : 'EvaluateCalibration',
                    'evaluate_on' : [eval_mode],
                    'model_kwargs_evaluate' : {
                        'temperature_scaling' : False,
                    },
                },
                apply_no_edges({
                    'type' : 'EvaluateCalibration',
                    'evaluate_on' : [eval_mode],
                    'model_kwargs_evaluate' : {
                        'temperature_scaling' : False,
                    },
                }),
                {
                    'type' : 'EvaluateCalibration',
                    'evaluate_on' : [eval_mode],
                    'model_kwargs_evaluate' : {
                        'temperature_scaling' : True,
                    },
                    'name' : '-temperature-scaling',
                },
                apply_no_edges({
                    'type' : 'EvaluateCalibration',
                    'evaluate_on' : [eval_mode],
                    'model_kwargs_evaluate' : {
                        'temperature_scaling' : True,
                    },
                    'name' : '-temperature-scaling',
                }),
                {
                    'type' : 'EvaluateEmpircalLowerLipschitzBounds',
                    'num_perturbations' : 20,
                    'min_perturbation' : .1,
                    'max_perturbation' : 10.0,
                    'num_perturbations_per_sample' : 5,
                    'seed' : 1337,
                    'perturbation_type' : 'noise',
                    'name' : 'noise',
                    'evaluate_on' : [eval_mode]
                },
                apply_no_edges({
                    'type' : 'EvaluateEmpircalLowerLipschitzBounds',
                    'num_perturbations' : 20,
                    'min_perturbation' : .1,
                    'max_perturbation' : 10.0,
                    'num_perturbations_per_sample' : 5,
                    'seed' : 1337,
                    'perturbation_type' : 'noise',
                    'name' : 'noise',
                    'evaluate_on' : [eval_mode]
                }),
            ]

            if ood_type == 'perturbations':
                # Build perturbed datasets
                pipeline += [
                    {
                        'type' : 'PerturbData',
                        'base_data' : f'ood-{eval_mode}',
                        'dataset_name' : f'ber-{eval_mode}',
                        'perturbation_type' : 'bernoulli',
                        'parameters' : {
                            'p' : 0.5,
                        },
                    },
                    {
                        'type' : 'PerturbData',
                        'base_data' : f'ood-{eval_mode}',
                        'dataset_name' : f'normal-{eval_mode}',
                        'perturbation_type' : 'normal',
                        'parameters' : {
                            'scale' : 1.0,
                        },
                    },
                ]
                ood_datasets = {'ber' : f'ber-{eval_mode}', 'normal' : f'normal-{eval_mode}'}
            else:
                ood_datasets = {'loc' : f'ood-{eval_mode}'}
            
            for ood_name, ood_dataset in ood_datasets.items():
                if ood_name == 'loc':
                    ood_args = {
                        'separate_distributions_by' : 'ood-and-neighbourhood',
                        'separate_distributions_tolerance' : 0.1,
                    }
                else:
                    ood_args = {}

                for suffix, args in (
                    ('-no-edges', {
                    'model_kwargs_evaluate' : {'remove_edges' : True}
                    }), 
                    ('', {})
                    ):
                    pipeline += [
                    {
                        'type' : 'EvaluateAccuracy',
                        'evaluate_on' : [ood_dataset],
                        'name' : f'{ood_name}{suffix}',
                    } | deepcopy(args) | deepcopy(ood_args),
                    {
                        'type' : 'EvaluateSoftmaxEntropy',
                        'evaluate_on' : [ood_dataset],
                        'name' : f'{ood_name}{suffix}',
                    } | deepcopy(args) | deepcopy(ood_args),
                    {
                        'type' : 'EvaluateLogitEnergy',
                        'evaluate_on' : [ood_dataset],
                        'name' : f'{ood_name}{suffix}',
                    } | deepcopy(args) | deepcopy(ood_args),
                    # {
                    #     'type' : 'LogInductiveFeatureShift',
                    #     'data_before' : 'train',
                    #     'data_after' : ood_dataset,
                    #     'name' : f'{ood_name}{suffix}',
                    # } | deepcopy(args) | deepcopy(ood_args),
                    # {
                    #     'type' : 'LogInductiveSoftmaxEntropyShift',
                    #     'data_before' : 'train',
                    #     'data_after' : ood_dataset,
                    #     'name' : f'{ood_name}{suffix}',
                    # } | deepcopy(args) | deepcopy(ood_args),
                ]

                    # Feature space densities
                    # GPC
            for member in pipeline:
                if 'name' in member:
                    member['name'] += f'_{eval_mode}'
                else:
                    member['name'] = eval_mode
                member['log_plots'] = False

            pipeline_all_eval_modes += pipeline

    
        # Vanilla model
        subcfg = {
            'fixed' : {
                'evaluation.pipeline' : deepcopy(pipeline_all_eval_modes),
            }
        }
            
        subcfg['fixed']['run.name'] = 'ensemble-dataset:{1}-setting:{0}-ood_type:' + ood_type_short
        subcfg['fixed']['data.ood_type'] = ood_type

        key = f'{ood_type}_ensemble'
        assert key not in cfg, f'Config {key} is already defined.'
        cfg[key] = subcfg
        
if __name__ == '__main__':
    build()