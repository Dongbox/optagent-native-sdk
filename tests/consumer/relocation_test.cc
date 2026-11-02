#include <cmath>
#include <string>

#include "Highs.h"
#include "absl/numeric/int128.h"
#include "google/protobuf/struct.pb.h"
#include "optagent_cpsat/session.h"
#include "ortools/sat/cp_model.pb.h"
#include "ortools/sat/sat_parameters.pb.h"

int main() {
  google::protobuf::Struct value, restored;
  (*value.mutable_fields())["status"].set_string_value("ok");
  if (!restored.ParseFromString(value.SerializeAsString()) ||
      restored.fields().at("status").string_value() != "ok")
    return 1;
  if (absl::Uint128Low64(absl::MakeUint128(1, 2)) != 2) return 2;
  Highs highs;
  highs.setOptionValue("output_flag", false);
  highs.setOptionValue("presolve", "off");
  if (highs.setOptionValue("solver", "hipo") != HighsStatus::kOk) return 3;
  HighsLp lp;
  lp.num_col_ = 2;
  lp.num_row_ = 1;
  lp.col_cost_ = {1, 2};
  lp.col_lower_ = {0, 0};
  lp.col_upper_ = {kHighsInf, kHighsInf};
  lp.row_lower_ = {1};
  lp.row_upper_ = {1};
  lp.a_matrix_.format_ = MatrixFormat::kColwise;
  lp.a_matrix_.start_ = {0, 1, 2};
  lp.a_matrix_.index_ = {0, 0};
  lp.a_matrix_.value_ = {1, 1};
  if (highs.passModel(lp) != HighsStatus::kOk ||
      highs.run() != HighsStatus::kOk ||
      highs.getModelStatus() != HighsModelStatus::kOptimal ||
      std::abs(highs.getObjectiveValue() - 1) > 1e-6)
    return 4;
  namespace cp = operations_research::sat;
  cp::CpModelProto model;
  auto* variable = model.add_variables();
  variable->add_domain(0);
  variable->add_domain(1);
  model.mutable_objective()->add_vars(0);
  model.mutable_objective()->add_coeffs(-1);
  cp::SatParameters parameters;
  parameters.set_num_search_workers(1);
  optagent::cpsat_sdk::Session session;
  cp::CpSolverResponse response;
  std::string error;
  if (session.Run(model, parameters, {}, &response, &error) !=
          optagent::cpsat_sdk::RunStatus::kOk ||
      !error.empty() || response.status() != cp::OPTIMAL ||
      response.solution(0) != 1)
    return 5;
  return 0;
}
