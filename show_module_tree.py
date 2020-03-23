from __future__ import absolute_import
from __future__ import print_function
import sys
import os
from optparse import OptionParser

# the next line can be removed after installation
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyverilog.utils.version
from pyverilog.vparser.parser import parse

from pyverilog.vparser.ast import Node
from pyverilog.vparser.ast import ModuleDef
from pyverilog.vparser.ast import Instance
from pyverilog.vparser.ast import Input
from pyverilog.vparser.ast import Output
from pyverilog.vparser.ast import PortArg
from pyverilog.vparser.ast import Identifier
from pyverilog.vparser.ast import Partselect
from pyverilog.vparser.ast import IntConst
def debug(x):
    print(x, file=sys.stderr, end=' ')
    return

def module_tree(self, buf=sys.stdout, offset=0, showlineno=True):
    indent = 2
    lead = ' ' * offset

    if (self.__class__.__name__== 'ModeleDef'
     or self.__class__.__name__== 'ModuleDef'
      ):
        buf.write(lead + self.__class__.__name__ + ': ')

        if self.attr_names:
            if True:
                nvlist = [(n, getattr(self, n)) for n in self.attr_names]
                attrstr = ', '.join('%s=%s' % (n, v) for (n, v) in nvlist)
            buf.write(attrstr)

        if showlineno:
            buf.write(' (at %s)' % self.lineno)

        buf.write('\n')

    for c in self.children():
        c.module_tree(buf, offset + indent, showlineno)


def get_node(self, fn, buf=sys.stderr, offset=0, showlineno=True, ret=[]):

    indent = 2
    lead = ' ' * offset
    
    if (fn(self)):
        ret.append(self)
        buf.write(lead + self.__class__.__name__ + ': ')
        if self.attr_names:
            nvlist = [(n, getattr(self, n)) for n in self.attr_names]
            attrstr = ', '.join('%s=%s' % (n, v) for (n, v) in nvlist)
            buf.write(attrstr)
        if showlineno:
            buf.write(' (at %s)' % self.lineno)
        buf.write('\n')
        return

    for c in self.children():
        c.get_node(fn, buf, offset + indent, showlineno, ret)
    return ret

gen_dot_header = \
"""
digraph {
    rankdir="LR";
    overlap = false;
    splines = true;
    node [shape = box, height=0.1];
    edge [labelfloat=false];
"""
#   node[width=0.0, height=0.0, label="" shape=point];
gen_dot_footer = "}"
Instance.id_ = 0
def gen_dot(self, ls_module, prefix=''):
    """
    TODO: visitorパターンにrefactorする
    ↓ 2つを分離する点がvisitor patternを知ってる人にはわかりやすいかも
    - selfに対するdot生成処理
    - ls_instanceやportを呼び出す部分
    """
    debug("gen_dot:")
    debug(self)
    debug('\n')
    debug("ls_module:")
    debug(ls_module)
    debug('\n')

    def get_module_def(inst, ls_module):
        assert (inst, Instance)
        emsg = "\n" \
             + "multiple declear of module `" + str(inst.module) + "` is detected.\n" \
             + "but this check is NOT enough 'cause of TOP module multiple declear.\n"
        ll = [i for i in ls_module if isinstance(i, ModuleDef) and i.name == inst.module]
        assert (len(ll) == 1 or len(ll) == 0), emsg
        if len(ll) == 1:
            return ll[0]
        else :
            return None

    def is_output_port_estimate(p, i, module_def=None):
        assert (isinstance(p, PortArg))
        assert (isinstance(i, Instance))
        assert (module_def == None)

        """pがoutput_portだと推測できる条件"""
        portname = p.portname
        if portname[0] == 'o':
            return True
        if portname[0] == 'q':
            return True
        return False

    def is_output_port_with_module_def(p, i, module_def):
        assert (isinstance(p, PortArg))
        assert (isinstance(i, Instance))
        assert (isinstance(module_def, ModuleDef))

        portname = p.portname
        for o in module_def.ls_output:
            if o.name == portname:
                return True
        return False

    def print_connect(src_node_name, prefix, instance, port):
        d_prefix = prefix + "_" + instance.name
        d_node_name = d_prefix + "_" + port.portname
        wire_name = " " 
        print ("%s -> %s[label = \"%s\"];"%(src_node_name, d_node_name, wire_name)) 

    if isinstance(self, ModuleDef):
        """
        下位モジュール
        """
        for i in self.ls_instance:
            i.gen_dot(ls_module, prefix)
        """
        入力ポート/出力ポートを全てdot_lang:nodeとして表現する
        """
        for i in self.ls_input + self.ls_output:
            node_name = prefix + "_" + i.name
            node_label = i.name
            if hasattr_parents(i, 'width.msb') \
                and hasattr_parents(i, 'width.lsb'):
                msb = i.width.msb.value
                lsb = i.width.lsb.value
                node_label += "[%s:%s]"%(msb,lsb)
            print ("%s[label = \"%s\"];"%(node_name, node_label))
        """
        self(Moduledef) input port(s) dummy node(branch)
        """
        for i in self.ls_input:
            s_node_name = prefix + "_" + i.name
            br_node_name = s_node_name + "_input_br"
            print ("%s[width=0.01, height=0.01, shape=point];"%br_node_name)
            print ("%s -> %s[dir = none];"%(s_node_name, br_node_name))

        """
        [課題]
        下位モジュールが提供されない場合がある(セルライブラリなど)
        下位モジュールの出力ポートであることを判定できない

        [解決]
        とにかく、output_portはoutput_portであると確定させる
        下位モジュールが提供されない場合
        アドホックな条件(あるポートがoutput_portと推測できる条件)を列挙しておき、
        その条件を満たすならoutput_port
        満たさないならinput_portと推測することにする

        [理由] 
        あるoutput_portがoutput_portだと認識されるまで
        そのoutput_portの対向input_portは、edgeを定義できないから

        [例]
        if instanceのモジュール名 == CLKINV && port名 == x:
            -> 判定：output_port, branch_nodeをprint()してcontinue, edgeはprint()しない
            ...
        elif instanceのモジュール名 == SRFF && port名 == q:
            -> 判定：output_port, branch_nodeをprint()してcontinue, edgeはprint()しない
        else:
            pass

        [擬似コード]
        for i in (all instance)：
            [1] if モジュール定義があるinstance
            for p in (all input/output_port)：
                if p is output_port:
                    -> 判定：output_port, branch_nodeをprint()してcontinue, edgeはprint()しない
                else:
                    pass
            [2] else (モジュール定義がないinstance)
            for p in (all input/output_port)：
               (同上, input_port/output_portの判定方法だけが異なる
                - Moduledefのls_input/ls_outputを逆引きするか
                - 推測(module名とport名に基づく) 
                -> 関数ポインタとして渡してやれば良い

        for i in (all instance)：
            [1] if モジュール定義があるinstance
            for p in (all input/output_port)：
                if p is input_port:
                    [1] ```process for input_port```
                    [1-1] if 接続先 is Const?
                       -> 判定：inputport, edgeをprint()してcontinue
                    [1-2] if 接続先 is Parent_Moduleのinput_port?
                       -> 判定：inputport, edgeをprint()してcontinue
                    [1-3] if 接続先 is other instanceのoutput_port?
                       -> 判定：input_port, edgeをprint()してcontinue
                else:
                    pass

            [2] else (モジュール定義がないinstance)
            for p in (all input/output_port)：
               (同上, input_port/output_portの判定方法だけが異なる
                - Moduledefのls_input/ls_outputを逆引きするか
                - 推測(module名とport名に基づく) 
                -> 関数ポインタとして渡してやれば良い
        """

        """submodule.output_port"""
        for i in self.ls_instance:
            module_def = get_module_def(i, ls_module)
            if module_def == None:
                is_output_port = is_output_port_estimate
            else:
                is_output_port = is_output_port_with_module_def
            for p in i.portlist:
                if is_output_port(p, i, module_def):
                    s_node_name = prefix + "_" + i.name + "_" + p.portname
                    br_node_name = s_node_name + "_output_br"
                    print ("%s[width=0.01, height=0.01, shape=point];"%br_node_name)
                    print ("%s -> %s[dir = none];"%(s_node_name, br_node_name))
                else:
                    pass
        """submodule.input_port"""
        for i in self.ls_instance:
            module_def = get_module_def(i, ls_module)
            if module_def == None:
                is_output_port = is_output_port_estimate
            else:
                is_output_port = is_output_port_with_module_def
            for p in i.portlist:
                assert(hasattr(p, 'argname'))
                if not is_output_port(p, i, module_def):
                    """[1] ```process for input_port```"""
                    if isinstance(p.argname, IntConst):
                        """[1-1] if 接続先 is Const?"""
                        ### TODO:bit幅チェック
                        const_value = p.argname.value
                        const_node_name = prefix + "_const_" + i.name + p.portname
                        print ("%s[label = \"%s\"];"%(const_node_name, const_value))
                        print_connect(const_node_name, prefix, i, p)
                        continue
                    elif isinstance(p.argname, Identifier) or isinstance(p.argname, Partselect):
                        """[1-2] if 接続先 is Parent_Moduleのinput_port?"""
                        """[1-3] if 接続先 is other instanceのoutput_port?"""
                        arg_wire_name = p.argname.name if isinstance(p.argname, Identifier) else p.argname.var.name
                        ll = [i for i in self.ls_input if i.name == arg_wire_name]
                        assert (len(ll) == 1 or len(ll) == 0), "fuck"
                        if (len(ll) == 1):
                            br_node_name = prefix + "_" + ll[0].name + "_input_br"
                            print_connect(br_node_name, prefix, i, p)
                            continue
                        for ii in self.ls_instance:
                            module_def = get_module_def(ii, ls_module)
                            if module_def == None:
                                is_output_port = is_output_port_estimate
                            else:
                                is_output_port = is_output_port_with_module_def
                            for pp in ii.portlist:
                                assert(hasattr(pp, 'argname'))
                                if is_output_port(pp, ii, module_def) \
                                   and ( \
                                       isinstance(pp.argname, Identifier) or isinstance(pp.argname, Partselect) \
                                   ):
                                    s_arg_wire_name = pp.argname.name if isinstance(pp.argname, Identifier) else pp.argname.var.name
                                    if s_arg_wire_name == arg_wire_name:
                                        br_node_name = prefix + "_" + ii.name + "_" + pp.portname + "_output_br"
                                        print_connect(br_node_name, prefix, i, p)
                    else:
                        pass
                else:
                    pass
        return

    elif isinstance(self, Instance):
        print ('subgraph cluster%d {'%Instance.id_)
        print ("  graph [label = \"%s:%s\"];"%(self.module, self.name))
        print ("tmp%d[width=0.0, height=0.0, shape=point];"%Instance.id_)

        Instance.id_ += 1
        ll = [i for i in ls_module if isinstance(i, ModuleDef) and i.name == self.module]
        debug("ll = [i for i in ls_module if isinstance(i, ModuleDef) and i.name == self.module]:")
        debug(ll)
        debug(self.module)
        debug('\n')
        emsg = "\n" \
             + "multiple declear of module `" + str(self.module) + "` is detected.\n" \
             + "but this check is NOT enough 'cause of TOP module multiple declear.\n"
        assert (len(ll) == 1 or len(ll) == 0), emsg
        if len(ll) == 1:
            prefix += "_" + self.name
            ll[0].gen_dot(ls_module, prefix)
        else :
            pass
        print ('}')
        return

    else:
        return

def hasattr_parents(obj, attrs):
    assert (isinstance(attrs, str))
    ls_attr = attrs.split('.')
    for attr in ls_attr:
        if hasattr(obj, attr):
            obj = getattr(obj, attr)
        else:
            return False
    return True

def main():
    INFO = "Verilog code parser"
    VERSION = pyverilog.utils.version.VERSION
    USAGE = "Usage: python example_parser.py file ..."

    def showVersion():
        print(INFO)
        print(VERSION)
        print(USAGE)
        sys.exit()

    optparser = OptionParser()
    optparser.add_option("-v","--version",action="store_true",dest="showversion",
                         default=False,help="Show the version")
    optparser.add_option("-I","--include",dest="include",action="append",
                         default=[],help="Include path")
    optparser.add_option("-D",dest="define",action="append",
                         default=[],help="Macro Definition")
    (options, args) = optparser.parse_args()

    filelist = args
    if options.showversion:
        showVersion()

    for f in filelist:
        if not os.path.exists(f): raise IOError("file not found: " + f)

    if len(filelist) == 0:
        showVersion()

    Node.get_node= get_node
    Node.gen_dot = gen_dot
    ast, directives = parse(filelist,
                            preprocess_include=options.include,
                            preprocess_define=options.define)
    ls_module = []
    ast.get_node(lambda x: isinstance(x, ModuleDef), ret=ls_module)
    for m in ls_module:
        m.ls_input = []
        m.ls_output = []
        m.ls_instance = []
        m.get_node(lambda x: isinstance(x, Input), ret=m.ls_input)
        m.get_node(lambda x: isinstance(x, Output), ret=m.ls_output)
        m.get_node(lambda x: isinstance(x, Instance), ret=m.ls_instance)
        for i in m.ls_instance:
            i.ls_port = []
            i.get_node(lambda x: isinstance(x, PortArg), ret=i.ls_port)
    print (gen_dot_header)
    ls_module[0].gen_dot(ls_module)
    print (gen_dot_footer)
    
if __name__ == '__main__':
    main()
