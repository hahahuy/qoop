import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import typing
import types
import qiskit
from ..core import gradient, optimizer, metric, measure, ansatz, state
from ..backend import utilities

class QuantumCompilation():
    def __init__(self) -> None:
        self.u = None
        self.vdagger = None
        self.is_trained = False
        self.optimizer = None
        self.loss_func = None
        self.thetas = None
        self.thetass = []
        self.metrics = {}
        self.metrics_func = {}
        self.kwargs = None
        self.is_evolutional = False
        self.num_steps = 0
        return

    def __init__(self, 
                u: qiskit.QuantumCircuit, 
                vdagger: qiskit.QuantumCircuit | np.ndarray, 
                optimizer: typing.Union[types.FunctionType, str] = 'adam', 
                metrics_func: typing.List[types.FunctionType] | typing.List[str] = ['loss_fubini_study', 'compilation_trace_distances', 'compilation_trace_fidelities'], 
                thetas: np.ndarray = np.array([]), **kwargs):
        """_summary_

        Args:
            - u (qiskit.QuantumCircuit]): In quantum state preparation problem, this is the ansatz. In tomography, this is the circuit that generate random Haar state.
            - vdagger (qiskit.QuantumCircuit]): In quantum tomography problem, this is the ansatz. In state preparation, this is the circuit that generate random Haar state.
            - optimizer (typing.Union[types.FunctionType, str]): You can put either string or function here. If type string, qcompilation produces some famous optimizers such as: 'sgd', 'adam', 'qng-fubini-study', 'qng-qfim', 'qng-adam'.
            - metrics_func (typing.Union[types.FunctionType, str]): You can put either string or function here. If type string, qcompilation produces some famous optimizers such as: 'loss_basic'  (1 - p0) and 'loss_fubini_study' (\sqrt{(1 - p0)}).
            - thetas (np.ndarray, optional): initial parameters. Note that it must fit with your ansatz. Defaults to np.array([]).
        """
        self.thetass = []
        self.metrics = {}
        self.metrics_func = {}
        self.kwargs = None
        self.is_evolutional = False
        self.num_steps = 0
        self.set_u(u)
        if isinstance(vdagger, np.ndarray):
            vdagger = state.specific(vdagger).inverse()
        self.set_vdagger(vdagger)
        self.set_optimizer(optimizer)
        self.set_metrics_func(metrics_func)
        self.set_kwargs(**kwargs)
        self.set_thetas(thetas)
        return
    
    @staticmethod
    def prepare(target_state: np.ndarray):
        num_qubits = int(np.log2(target_state.shape[0]))
        vdagger = state.specific(target_state).inverse()
        compiler = QuantumCompilation(ansatz.g2gnw(num_qubits, 2), vdagger)
        return compiler
    def set_u(self, _u: qiskit.QuantumCircuit) -> None:
        """In quantum state preparation problem, this is the ansatz. In tomography, this is the circuit that generate random Haar state.

        Args:
            - _u (typing.Union[types.FunctionType, qiskit.QuantumCircuit]): init circuit
        """
        if isinstance(_u, qiskit.QuantumCircuit):
            self.u = _u
        else:
            raise ValueError('The U part must be a determined quantum circuit')
        return

    def set_vdagger(self, _vdagger) -> None:
        """In quantum state tomography problem, this is the ansatz. In state preparation, this is the circuit that generate random Haar state.

        Args:
            - _vdagger (qiskit.QuantumCircuit): init circuit
        """
        if isinstance(_vdagger, qiskit.QuantumCircuit):
            self.vdagger = _vdagger
        else:
            raise ValueError(
                'The V dagger part must be a determined quantum circuit')
        return

    def set_metrics_func(self, _metrics_func: typing.List[types.FunctionType] | typing.List[str]) -> None:
        """Set the metric function for compiler

        Args:
            - _metrics_func (typing.List[types.FunctionType] | typing.List[str])

        Raises:
            ValueError: when you pass wrong type
        """
        for _metric_func in _metrics_func:
            if callable(_metric_func):
                self.metrics_func[_metric_func.__name__] = _metric_func
            elif isinstance(_metric_func, str):
                self.metrics_func[_metric_func] = getattr(metric, _metric_func)
            else:
                raise ValueError(
                    'The metric function must be a function f: u, vdagger, thetas -> metric value or string in qsee.core.metric or self-define')
        return

    def set_optimizer(self, _optimizer: typing.Union[types.FunctionType, str]) -> None:
        """Change the optimizer of the compiler

        Args:
            - _optimizer (typing.Union[types.FunctionType, str])

        Raises:
            ValueError: when you pass wrong type
        """
        if callable(_optimizer):
            self.optimizer = _optimizer
        elif isinstance(_optimizer, str):
            self.optimizer = getattr(optimizer, _optimizer)
        else:
            raise ValueError(
                'The optimizer must be a function f: thetas -> thetas or string in qsee.core.optimizer or self-define')
        return

    def set_num_steps(self, _num_steps: int) -> None:
        """Set the number of iteration for compiler

        Args:
            - _num_steps (int): number of iterations

        Raises:
            ValueError: when you pass a nasty value
        """
        if _num_steps > 0 and isinstance(_num_steps, int):
            self.num_steps = _num_steps
        else:
            raise ValueError(
                'Number of iterations must be an integer, take example: 10 or 100.')
        return

    def set_thetas(self, _thetas: np.ndarray) -> None:
        """Set parameter, it will be updated at each iteration

        Args:
            _thetas (np.ndarray): parameter for u or vdagger
        """
        if isinstance(_thetas, np.ndarray):
            self.thetas = _thetas
        else:
            raise ValueError('The parameter must be numpy array')
        return

    def set_kwargs(self, **kwargs) -> None:
        """Arguments supported for u or vdagger only. Ex: number of layer
        """
        self.__dict__.update(**kwargs)
        self.kwargs = kwargs
        return

    def fit(self, num_steps: int = 100, metrics_name: typing.List[str] = 'compilation', verbose: int = 0) -> None:
        """Optimize the thetas parameters

        Args:
            - num_steps: number of iterations
            - verbose (int, optional): 0, 1, or 2. Verbosity mode. 0 = silent, 1 = progress bar, 2 = one line per 10 steps. Verbose 1 is good for timing training time, verbose 2 if you want to log loss values to a file. Please install package tdqm if you want to use verbose 1. 
            - metrics (List[str]): list of metric name that you want, take example, ['compilation', 'gibbs']
        """
        self.num_steps = num_steps
        if len(self.thetas) == 0:
            if (len(self.u.parameters)) > 0:
                self.thetas = np.ones(len(self.u.parameters))
            else:
                self.thetas = np.ones(len(self.vdagger.parameters))
        self.is_trained = True

        if verbose == 1:
            bar = utilities.ProgressBar(max_value=num_steps, disable=False)
        uvaddager = self.u.compose(self.vdagger)
        for i in range(0, num_steps):
            grad_loss = gradient.grad_loss(uvaddager, self.thetas)
            optimizer_name = self.optimizer.__name__
            if optimizer_name == 'sgd':
                optimizer_params = [grad_loss]
            elif optimizer_name == 'adam':
                if i == 0:
                    m, v1 = list(np.zeros(self.thetas.shape[0])), list(
                        np.zeros(self.thetas.shape[0]))
                optimizer_params = [m, v1, i, grad_loss]

            elif 'qng' in optimizer_name:
                grad_psi1 = gradient.grad_psi(uvaddager, self.thetas,
                                            r=1 / 2,
                                            s=np.pi)
                qc_binded = uvaddager.assign_parameters(self.thetas)
                psi = qiskit.quantum_info.Statevector.from_instruction(qc_binded).data
                psi = np.expand_dims(psi, 1)
                if optimizer_name == 'qng_fubini_study':
                    G = gradient.qng(qc_binded)
                    optimizer_params = [G, grad_loss]
                if optimizer_name == 'qng_fubini_hessian':
                    G = gradient.qng_hessian(uvaddager)
                    optimizer_params = [G, grad_loss]
                if optimizer_name == 'qng_fubini_study_scheduler':
                    G = gradient.qng(uvaddager)
                    optimizer_params = [G, grad_loss, i]
                if optimizer_name == 'qng_qfim':
                    optimizer_params = [psi, grad_psi1, grad_loss]
                if optimizer_name == 'qng_adam':
                    if i == 0:
                        m, v1 = list(np.zeros(self.thetas.shape[0])), list(
                            np.zeros(self.thetas.shape[0]))
                    optimizer_params = [m, v1, i, psi, grad_psi1, grad_loss]
            
            self.thetas = self.optimizer(self.thetas, *optimizer_params)
            self.thetass.append(self.thetas.copy())
            if verbose == 1:
                bar.update(1)
            if verbose == 2 and i % 10 == 0:
                print(f"Step {i} ...")

        if verbose == 1:
            bar.close()
        self.calculate_metrics()
        return

    def calculate_metrics(self) -> None:
        for metric in self.metrics_func:
            metric_params = [self.u, self.vdagger, self.thetass]
            metric_func: types.FunctionType = self.metrics_func[metric]
            self.metrics[metric] = metric_func(*metric_params)
        return
    def plot(self) -> None:
        """Plot coressponding metrics.

        Args:
            metrics (typing.List[str]): can be loss, compilation, gibbs or ce
        """
        for metric in self.metrics:
            plt.plot(self.metrics[metric], label = metric)
        plt.ylabel("Value")
        plt.xlabel('Num. iteration')
        plt.legend()
        return

    def plot_animation(self, interval: int = 100, file_name: str = 'test.gif'):
        """_summary_

        Args:
            interval (int, optional): _description_. Defaults to 100.
            file_name (str, optional): _description_. Defaults to 'test.gif'.
        """
        
        x = np.linspace(0, int(self.num_steps), int(self.num_steps))
        y1 = self.loss_values
        y2 = self.compilation_fidelities
        y3 = self.compilation_traces
        fig, ax = plt.subplots()
        ax.set_xlim(int(-self.num_steps*0.05), int(self.num_steps*1.05))
        ax.set_ylim(-0.05, 1.05)
        loss_text = ax.text(0, 0, "", fontsize=12)
        fid_text = ax.text(0, 0, "", fontsize=12)
        trace_text = ax.text(0, 0, "", fontsize=12)
        plt.ylabel("Loss values")
        plt.xlabel('Num. iteration')
        xs = []
        ys1, ys2, ys3 = [], [], []

        def update(i):
            xs.append(x[i])
            ys1.append(y1[i])
            ys2.append(y2[i])
            ys3.append(y3[i])
            ax.plot(xs, ys1, color='blue', label='Loss value')
            ax.plot(xs, ys2, color='red', label='Fidelity')
            ax.plot(xs, ys3, color='green', label='Trace')
            loss_text.set_position([xs[i], ys1[i]])
            loss_text.set_text('Loss: ' + str(np.round(ys1[i], 2)))
            fid_text.set_position([xs[i], ys2[i]])
            fid_text.set_text('Fidelity: ' + str(np.round(ys2[i], 2)))
            trace_text.set_position([xs[i], ys3[i]])
            trace_text.set_text('Trace: ' + str(np.round(ys3[i], 2)))
        animator = animation.FuncAnimation(fig, update,
                                           interval=interval, repeat=False)
        animator.save(file_name)


    def reset(self):
        """Delete all current property of compiler
        """
        self.u = None
        self.vdagger = None
        self.is_trained = False
        self.optimizer = None
        self.loss_func = None
        self.num_steps = 0
        self.thetas = None
        self.thetass = []
        self.metrics = {}
        self.metrics_func = {}
        return