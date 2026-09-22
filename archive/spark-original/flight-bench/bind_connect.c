#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static int (*real_connect)(int, const struct sockaddr*, socklen_t);

static int bind_local(int sockfd, const char* bind_addr) {
  int domain = 0;
  socklen_t dlen = sizeof(domain);
  if (getsockopt(sockfd, SOL_SOCKET, SO_DOMAIN, &domain, &dlen) != 0) {
    domain = AF_INET;
  }

  const char* bind_dev = getenv("BIND_DEV");
#ifdef SO_BINDTODEVICE
  if (bind_dev && bind_dev[0]) {
    if (setsockopt(sockfd, SOL_SOCKET, SO_BINDTODEVICE, bind_dev,
                   (socklen_t)strlen(bind_dev) + 1) != 0) {
      if (getenv("BIND_DEBUG")) {
        fprintf(stderr, "bind_connect: SO_BINDTODEVICE(%s): %s\n", bind_dev,
                strerror(errno));
      }
    }
  }
#endif

  int one = 1;
  (void)setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

  if (domain == AF_INET6) {
    struct sockaddr_in6 local;
    memset(&local, 0, sizeof(local));
    local.sin6_family = AF_INET6;
    local.sin6_port = 0;
    char mapped[64];
    snprintf(mapped, sizeof(mapped), "::ffff:%s", bind_addr);
    if (inet_pton(AF_INET6, mapped, &local.sin6_addr) != 1) {
      fprintf(stderr, "bind_connect: invalid IPv6 mapped BIND_ADDR=%s\n",
              bind_addr);
      return -1;
    }
    int v6only = 0;
    (void)setsockopt(sockfd, IPPROTO_IPV6, IPV6_V6ONLY, &v6only, sizeof(v6only));
    if (bind(sockfd, (struct sockaddr*)&local, sizeof(local)) != 0) {
      if (errno != EINVAL && errno != EISCONN && errno != EADDRINUSE) {
        fprintf(stderr, "bind_connect: bind6(%s) failed: %s\n", bind_addr,
                strerror(errno));
      }
      return -1;
    }
  } else {
    struct sockaddr_in local;
    memset(&local, 0, sizeof(local));
    local.sin_family = AF_INET;
    local.sin_port = 0;
    if (inet_pton(AF_INET, bind_addr, &local.sin_addr) != 1) {
      fprintf(stderr, "bind_connect: invalid BIND_ADDR=%s\n", bind_addr);
      return -1;
    }
    if (bind(sockfd, (struct sockaddr*)&local, sizeof(local)) != 0) {
      if (errno != EINVAL && errno != EISCONN && errno != EADDRINUSE) {
        fprintf(stderr, "bind_connect: bind(%s) failed: %s\n", bind_addr,
                strerror(errno));
      }
      return -1;
    }
  }
  if (getenv("BIND_DEBUG")) {
    fprintf(stderr, "bind_connect: bound fd=%d to %s dev=%s domain=%d\n", sockfd,
            bind_addr, bind_dev ? bind_dev : "-", domain);
  }
  return 0;
}

int connect(int sockfd, const struct sockaddr* addr, socklen_t addrlen) {
  if (!real_connect) {
    real_connect = (int (*)(int, const struct sockaddr*, socklen_t))dlsym(
        RTLD_NEXT, "connect");
  }
  const char* bind_addr = getenv("BIND_ADDR");
  if (bind_addr && bind_addr[0] && addr &&
      (addr->sa_family == AF_INET || addr->sa_family == AF_INET6)) {
    (void)bind_local(sockfd, bind_addr);
  }
  return real_connect(sockfd, addr, addrlen);
}
