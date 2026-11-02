#include <functional>
#include <iostream>
#include <string>
#include <vector>

#include "absl/base/options.h"

#define SDK_STRINGIFY_INNER(value) #value
#define SDK_STRINGIFY(value) SDK_STRINGIFY_INNER(value)

int main() {
#if defined(_LIBCPP_VERSION)
  const char* library = "libc++";
  constexpr int abi = _LIBCPP_ABI_VERSION;
#elif defined(__GLIBCXX__)
  const char* library = "libstdc++";
  constexpr int abi = _GLIBCXX_USE_CXX11_ABI;
#elif defined(_MSVC_STL_VERSION)
  const char* library = "msvc";
  constexpr int abi = _MSVC_STL_VERSION;
#else
#error Unsupported standard library
#endif
#if defined(_MSC_VER) && defined(_DLL)
  constexpr int dynamic_crt = 1;
#else
  constexpr int dynamic_crt = 0;
#endif
#if defined(_ITERATOR_DEBUG_LEVEL)
  constexpr int iterator_debug = _ITERATOR_DEBUG_LEVEL;
#else
  constexpr int iterator_debug = 0;
#endif
#if defined(_GLIBCXX_DEBUG)
  constexpr int debug_containers = 1;
#else
  constexpr int debug_containers = 0;
#endif
#if defined(_CPPUNWIND) || defined(__EXCEPTIONS)
  constexpr int exceptions = 1;
#else
  constexpr int exceptions = 0;
#endif
#if defined(_CPPRTTI) || defined(__GXX_RTTI)
  constexpr int rtti = 1;
#else
  constexpr int rtti = 0;
#endif
#if defined(__SANITIZE_ADDRESS__)
  constexpr int address_sanitizer = 1;
#elif defined(__has_feature)
#if __has_feature(address_sanitizer)
  constexpr int address_sanitizer = 1;
#else
  constexpr int address_sanitizer = 0;
#endif
#else
  constexpr int address_sanitizer = 0;
#endif
#if defined(__SANITIZE_THREAD__)
  constexpr int thread_sanitizer = 1;
#elif defined(__has_feature)
#if __has_feature(thread_sanitizer)
  constexpr int thread_sanitizer = 1;
#else
  constexpr int thread_sanitizer = 0;
#endif
#else
  constexpr int thread_sanitizer = 0;
#endif
  std::cout << "{\"stdlib\":\"" << library << "\",\"stdlib_abi\":" << abi
            << ",\"iterator_debug\":" << iterator_debug
            << ",\"debug_containers\":" << debug_containers
            << ",\"exceptions\":" << exceptions << ",\"rtti\":" << rtti
            << ",\"dynamic_crt\":" << dynamic_crt
            << ",\"address_sanitizer\":" << address_sanitizer
            << ",\"thread_sanitizer\":" << thread_sanitizer
            << ",\"pointer_size\":" << sizeof(void*)
            << ",\"string_size\":" << sizeof(std::string)
            << ",\"vector_size\":" << sizeof(std::vector<int>)
            << ",\"function_size\":" << sizeof(std::function<void()>)
            << ",\"absl_namespace\":\""
            << SDK_STRINGIFY(ABSL_OPTION_INLINE_NAMESPACE_NAME) << "\"}\n";
}
