#include <atomic>

#include "ortools/sat/cp_model.pb.h"
#include "ortools/sat/cp_model_checker.h"
#include "ortools/sat/cp_model_solver.h"
#include "ortools/sat/model.h"
#include "ortools/sat/parameters_validation.h"
#include "ortools/sat/sat_parameters.pb.h"
#include "ortools/util/time_limit.h"

// Static consumers may retain the native Model API used by OptAgent 1.3.0.
// Shared consumers use the SDK Session boundary instead.
int main() {
  namespace cp = operations_research::sat;
  cp::CpModelProto problem;
  auto* variable = problem.add_variables();
  variable->add_domain(0);
  variable->add_domain(1);
  problem.mutable_objective()->add_vars(0);
  problem.mutable_objective()->add_coeffs(-1);
  cp::SatParameters parameters;
  parameters.set_num_search_workers(1);
  if (!cp::ValidateCpModel(problem).empty() ||
      !cp::ValidateInputCpModel(parameters, problem).empty()) {
    return 1;
  }
  std::atomic<bool> stop{false};
  cp::Model native;
  native.Add(cp::NewSatParameters(parameters));
  native.GetOrCreate<operations_research::TimeLimit>()
      ->RegisterExternalBooleanAsLimit(&stop);
  bool observed = false;
  native.Add(cp::NewFeasibleSolutionObserver(
      [&](const cp::CpSolverResponse& response) {
        observed = response.solution_size() == 1;
      }));
  const auto response = cp::SolveCpModel(problem, &native);
  return response.status() == cp::OPTIMAL && response.solution(0) == 1 &&
                 observed
             ? 0
             : 2;
}
