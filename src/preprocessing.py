import random
import re
import os
import xml.etree.ElementTree as XMLParser

import numpy as np
import pandas as pd
from itertools import product

from model.loadxml import load_xml_to_cbn
from model.xml2dot import convert2dot
from model.variable import Event

dot_path = r'C:\Program Files (x86)/Graphviz2.38/bin/dot.exe'


def build_complete_model(tetrad_model, complete_model, random_seed):
    # read the original Tetrad model and transfer it to a deterministic SCM model with all the hidden variable

    dag = open(tetrad_model, 'r')
    complete_model = open(complete_model, 'w')

    # the dag is generated by Tetrad
    # due to the limitation of Tetrad, we fail to generate a deterministic model directly
    # so we generate a DAG with all hidden variables and randomly select the response
    # such that the resultant graph is deterministic
    random.seed(random_seed)
    flag = False
    for line in dag.readlines():
        if line.find('<cpt') != -1:
            flag = True
        if line.find('</cpt') != -1:
            flag = False
        if line.find('<cpt variable="U') != -1:
            flag = False

        if line.find('<row>') == -1 or flag == False:
            complete_model.write(line)
        else:
            start = re.findall(r'^\s*<row>', line)
            new_line = start[0]
            integers = re.findall(r'\d+\.\d+', line)
            new_integers = [0.0] * integers.__len__()
            choice = random.randint(0, 1000) % integers.__len__()
            new_integers[choice] = 1.0
            new_line += ' '.join(map(str, new_integers))
            end = re.findall(r'</row>$', line)
            new_line += end[0] + '\n'
            complete_model.write(new_line)

    complete_model.close()


def build_partial_model(tetrad_model, complete_model, partial_model):
    # read the SCM model and transfer it to a probabilistic model without all the hidden variable
    complete_model = load_xml_to_cbn(complete_model)

    # we load the original graph for modification
    observed_model = XMLParser.parse(tetrad_model)
    root = observed_model.getroot()

    # vars
    for v in list(root[0])[::- 1]:
        # remove exogenous variables from node list
        if v.attrib['name'].startswith('U'):
            root[0].remove(v)

    # causal graph
    for pf in list(root[1])[::- 1]:
        # remove exogenous variables
        if pf.attrib['name'].startswith('U'):
            root[1].remove(pf)
        else:
            # remove exogenous variables from parents
            for p in list(pf)[::-1]:
                if p.attrib['name'].startswith('U'):
                    pf.remove(p)

    # cpts
    for c in root[2][::- 1]:
        name = c.attrib['variable']
        # remove cpts of exogenous variables
        if name.startswith('U'):
            root[2].remove(c)
        else:
            # todo: double check
            # marginalize out the exogenous variables
            index = complete_model.v[name].index
            # we assume the endogenous variable only have an exogenous parent and its index is the smallest
            u_index = list(complete_model.index_graph.pred[index].keys())[-1]

            m, n = complete_model.cpts[index].shape
            assert n == complete_model.v[name].domain_size

            u_size = complete_model.v[u_index].domain_size

            # delete the extra rows
            del c[m // u_size:]
            c.attrib['numRows'] = str(m // u_size)

            cpt = pd.DataFrame(data=np.zeros((m // u_size, n)), columns=complete_model.cpts[index].columns)
            for i in range(m // u_size):
                # each new row is the weighted cpts
                u_cpt = complete_model.cpts[u_index]
                joint_cpt = complete_model.cpts[index].iloc[i * u_size:(i + 1) * u_size, :]
                cpt.iloc[i, :] = cpt.iloc[i, :] + np.dot(u_cpt, joint_cpt).reshape(n)
                c[i].text = ' '.join(map("{:.6f}".format, cpt.iloc[i]))

    observed_model.write(partial_model)


def find_a_seed(tetrad_model, complete_model, partial_model):
    def has_zero():
        fin = open(partial_model, 'r')
        for l in fin.readlines():
            if re.search(r'<row>.*0.000.*</row>', l):
                return True
        return False

    for i in range(0, 1000000):
        build_complete_model(tetrad_model, complete_model, random_seed=i)
        build_partial_model(tetrad_model, complete_model, partial_model)
        if not has_zero():
            print(i)


def preprocess(data_dir, temp_dir, seed=None):
    tetrad_model = data_dir + 'original_model.xml'
    complete_model = data_dir + 'complete_model.xml'
    partial_model = data_dir + 'observed_model.xml'
    complete_model_dot = temp_dir + 'complete.gv'
    complete_model_png = temp_dir + 'complete.png'
    observed_model_dot = temp_dir + 'observed.gv'
    observed_model_png = temp_dir + 'observed.png'

    if seed is None:
        find_a_seed(tetrad_model, complete_model, partial_model)
    else:
        build_complete_model(tetrad_model, complete_model, random_seed=seed)
        build_partial_model(tetrad_model, complete_model, partial_model)

        # save the graphical outputs to the temp folder
        # convert2dot(complete_model, complete_model_dot)
        # convert2dot(partial_model, observed_model_dot)
        # os.system('"%s" -Tpng %s -o %s' % (dot_path, complete_model_dot, complete_model_png))
        # os.system('"%s" -Tpng %s -o %s' % (dot_path, observed_model_dot, observed_model_png))

    pass


def test():
    ###############
    complete_cbn = load_xml_to_cbn(complete_model)

    US = complete_cbn.v['US']
    UW = complete_cbn.v['UW']
    UA = complete_cbn.v['UA']
    UY = complete_cbn.v['UY']

    S = complete_cbn.v['S']
    W = complete_cbn.v['W']
    A = complete_cbn.v['A']
    Y_hat = complete_cbn.v['Y']

    print('Generate using conditional cpts')
    for s in S.domains.get_all():
        p = 0.0
        for us in US.domains.get_all():
            p = p + complete_cbn.get_prob(Event({S: s}), Event({US: us})) * complete_cbn.get_prob(Event({US: us}), Event({}))
        print(p)
    print()

    for s, w in product(S.domains.get_all(), W.domains.get_all()):
        p = 0.0
        for uw in UW.domains.get_all():
            p = p + complete_cbn.get_prob(Event({W: w}), Event({UW: uw, S: s})) * complete_cbn.get_prob(Event({UW: uw}), Event({}))
        print(p)
    print()

    for w, a in product(W.domains.get_all(), A.domains.get_all()):
        p = 0.0
        for ua in UA.domains.get_all():
            p = p + complete_cbn.get_prob(Event({A: a}), Event({UA: ua, W: w})) * complete_cbn.get_prob(Event({UA: ua}), Event({}))
        print(p)
    print()

    for s, w, a, y in product(S.domains.get_all(), W.domains.get_all(), A.domains.get_all(), Y_hat.domains.get_all()):
        p = 0.0
        for uy in UY.domains.get_all():
            p = p + complete_cbn.get_prob(Event({Y_hat: y}), Event({UY: uy, S: s, W: w, A: a})) * complete_cbn.get_prob(Event({UY: uy}), Event({}))
        print(p)

    print()
    print()

    print('Generate using joint cpt')
    complete_cbn.build_joint_table()
    for s in S.domains.get_all():
        print(complete_cbn.get_prob(Event({S: s})))
    print()

    for s, w in product(S.domains.get_all(), W.domains.get_all()):
        print(complete_cbn.get_prob(Event({W: w}), Event({S: s})))
    print()

    for w, a in product(W.domains.get_all(), A.domains.get_all()):
        print(complete_cbn.get_prob(Event({A: a}), Event({W: w})))
    print()

    for s, w, a, y in product(S.domains.get_all(), W.domains.get_all(), A.domains.get_all(), Y_hat.domains.get_all()):
        print(complete_cbn.get_prob(Event({Y_hat: y}), Event({S: s, W: w, A: a})))
    print()
    print()

    partial_cbn = load_xml_to_cbn(partial_model)
    partial_cbn.build_joint_table()
    S = partial_cbn.v['S']
    W = partial_cbn.v['W']
    A = partial_cbn.v['A']
    Y_hat = partial_cbn.v['Y']

    print('Generate using partial SCM')
    for s in S.domains.get_all():
        print(partial_cbn.get_prob(Event({S: s}), Event({})))
    print()

    for s, w in product(S.domains.get_all(), W.domains.get_all()):
        print(partial_cbn.get_prob(Event({W: w}), Event({S: s})))
    print()

    for w, a in product(W.domains.get_all(), A.domains.get_all()):
        print(partial_cbn.get_prob(Event({A: a}), Event({W: w})))
    print()

    for s, w, a, y in product(S.domains.get_all(), W.domains.get_all(), A.domains.get_all(), Y_hat.domains.get_all()):
        print(partial_cbn.get_prob(Event({Y_hat: y}), Event({S: s, W: w, A: a})))
    print()
    print()

# the following code is designed for testing and may not work in final version
if __name__ == '__main__':
    data_dir = '../data/demo/'
    temp_dir = '../temp/demo/'

    preprocess(data_dir, temp_dir, seed=0)

    complete_model = data_dir + 'complete_model.xml'
    partial_model = data_dir + 'observed_model.xml'

    test()
