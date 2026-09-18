'use strict';
class ProviderFailure extends Error {
  constructor(resultClass,message){
    super(message);
    this.name='ProviderFailure';
    this.resultClass=resultClass;
    this.rateLimit=resultClass==='RATE_LIMIT';
    this.timeout=resultClass==='TIMEOUT';
  }
}
module.exports={ProviderFailure};
