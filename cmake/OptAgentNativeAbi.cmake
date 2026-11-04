function(optagent_native_check_abi prefix configuration)
  # try_compile otherwise defaults to Debug on MSVC, including /MDd and
  # checked iterators, even when the consuming project is a Release build.
  set(CMAKE_TRY_COMPILE_CONFIGURATION "${configuration}")
  try_compile(_sdk_abi_compatible
    SOURCE_FROM_CONTENT sdk_abi_check.cc "#include <optagent_native/abi.h>\nint main() {}\n"
    CMAKE_FLAGS "-DINCLUDE_DIRECTORIES=${prefix}/include"
      "-DCMAKE_CXX_STANDARD=20" "-DCMAKE_CXX_STANDARD_REQUIRED=ON"
    NO_CACHE OUTPUT_VARIABLE _sdk_abi_diagnostic)
  if(NOT _sdk_abi_compatible)
    message(FATAL_ERROR "Native SDK C++ ABI profile differs:\n${_sdk_abi_diagnostic}")
  endif()
endfunction()
